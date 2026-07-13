"""
Blender operators for the TopoFit addon.

This module defines all the `bpy.types.Operator` classes that perform the
core functionalities of the TopoFit addon, including landmark management,
symmetry operations, and mesh deformation.
"""
import bpy
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree
from collections import defaultdict
import heapq
import webbrowser
from .utils import (
    get_landmark_indices, generate_mirror_map, store_mirror_data, load_mirror_map,
    ensure_target_shape_key,
    invalidate_distance_cache,
    get_cached_distances,
    populate_distance_cache,
    build_adjacency,
    _distance_cache # Direct access to global cache for modal operator efficiency
)

# ---------------------------------------------------------------------------
# OPERATORS (OPERATING NATIVELY IN EDIT MODE)
# ---------------------------------------------------------------------------
class TOPOFIT_OT_show_help(bpy.types.Operator):
    """
    Opens the offline HTML documentation for the TopoFit addon in a web browser.
    """
    bl_idname = "topofit.show_help"
    bl_label = "TopoFit Help"
    bl_description = "Opens the addon's offline documentation in your web browser."

    def execute(self, context):
        """
        Executes the operator to open the help documentation.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success, {'CANCELLED'} if the file is not found.
        """
        import os
        addon_dir = os.path.dirname(__file__)
        doc_path = os.path.join(addon_dir, "doc", "help.html")

        if not os.path.exists(doc_path):
            self.report({'ERROR'}, f"Documentation file not found: {doc_path}")
            return {'CANCELLED'}
        
        url = 'file://' + os.path.abspath(doc_path)
        webbrowser.open(url)
        self.report({'INFO'}, f"Opening documentation: {url}")
        return {'FINISHED'}

class TOPOFIT_OT_create_target_key(bpy.types.Operator):
    """
    Creates a new shape key for storing deformations and activates it automatically.
    This ensures non-destructive editing away from the 'Basis' shape key.
    """
    bl_idname = "topofit.create_target_key"
    bl_label = "Create Reshape Key"
    bl_description = "Creates a new shape key (e.g., 'TopoFit_Target') and sets it as active for deformation."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh object.
        """
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        """
        Executes the operator to create and activate the target shape key.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success.
        """
        obj = context.active_object
        scene = context.scene
        target_key_name = scene.topofit_props.topofit_target_key_name
        ensure_target_shape_key(obj, target_key_name)
        self.report({'INFO'}, f"Created and activated target shape key: '{target_key_name}'.")
        return {'FINISHED'}

class TOPOFIT_OT_select_mirrored(bpy.types.Operator):
    """
    Selects the X-mirrored counterpart of each currently selected vertex
    on the active mesh in Edit Mode.
    """
    bl_idname = "topofit.select_mirrored"
    bl_label = "Select Mirrored"
    bl_description = "Selects symmetrical vertices across the X-axis for all currently selected vertices."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh object in Edit Mode.
        """
        return (context.active_object and context.active_object.type == 'MESH' and context.mode == 'EDIT_MESH')

    def execute(self, context):
        """
        Executes the operator to select mirrored vertices.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success.
        """
        obj = context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        bm.verts.ensure_lookup_table()
        
        kd = KDTree(len(bm.verts))
        for i, v in enumerate(bm.verts):
            kd.insert(v.co, i)
        kd.balance()
        
        to_mirror = [v for v in bm.verts if v.select]
        
        for v in to_mirror:
            mirrored_co = v.co.copy()
            mirrored_co.x *= -1
            _co, index, dist = kd.find(mirrored_co)
            # If a mirrored counterpart is found within tolerance and it's not the same vertex
            if dist < 1e-4 and index != v.index: # Use 1e-4 for tolerance
                bm.verts[index].select = True
        
        bmesh.update_edit_mesh(me)
        self.report({'INFO'}, f"Mirrored selection for {len(to_mirror)} vertices.")
        return {'FINISHED'}

class TOPOFIT_OT_add_to_landmarks(bpy.types.Operator):
    """
    Adds currently selected vertices to the "TopoFit_Landmarks" vertex group.
    Optionally auto-creates a target shape key if needed.
    """
    bl_idname = "topofit.add_to_landmarks"
    bl_label = "Add Selected to Landmarks"
    bl_description = "Adds selected vertices to the 'TopoFit_Landmarks' vertex group."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh object in Edit Mode
        with at least one vertex selected.
        """
        return (context.mode == 'EDIT_MESH' and context.active_object and
                context.active_object.type == 'MESH' and context.active_object.data.total_vert_sel > 0)
        
    def execute(self, context):
        """
        Executes the operator to add selected vertices to the landmark group.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success.
        """
        obj = context.active_object
        scene = context.scene
        
        # 1. AUTO-CREATE target key if configured, missing, or sitting on Basis
        if scene.topofit_props.topofit_auto_create_key:
            has_keys = obj.data.shape_keys is not None
            is_basis = has_keys and obj.active_shape_key_index == 0
            if not has_keys or is_basis:
                ensure_target_shape_key(obj, scene.topofit_props.topofit_target_key_name)
                self.report({'INFO'}, f"Auto-created and activated shape key: '{scene.topofit_props.topofit_target_key_name}'.")

        # 2. Get/create vertex group
        vg = obj.vertex_groups.get("TopoFit_Landmarks")
        if not vg:
            vg = obj.vertex_groups.new(name="TopoFit_Landmarks")
            
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        # Get active deform layer for vertex group weights
        weight_layer = bm.verts.layers.deform.active
        if not weight_layer:
            # If no deform layer, create one. This typically happens for new meshes.
            weight_layer = bm.verts.layers.deform.new()
            
        selected_count = 0
        for v in bm.verts:
            if v.select:
                v[weight_layer][vg.index] = 1.0 # Assign full weight to selected vertices
                selected_count += 1
                
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"Added {selected_count} vertices to 'TopoFit_Landmarks' group.")
        return {'FINISHED'}

class TOPOFIT_OT_remove_from_landmarks(bpy.types.Operator):
    """
    Removes currently selected vertices from the "TopoFit_Landmarks" vertex group.
    """
    bl_idname = "topofit.remove_from_landmarks"
    bl_label = "Remove Selected from Landmarks"
    bl_description = "Removes selected vertices from the 'TopoFit_Landmarks' vertex group."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh object in Edit Mode
        with at least one vertex selected.
        """
        return (context.mode == 'EDIT_MESH' and context.active_object and
                context.active_object.type == 'MESH' and context.active_object.data.total_vert_sel > 0)
        
    def execute(self, context):
        """
        Executes the operator to remove selected vertices from the landmark group.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success, {'CANCELLED'} if the group does not exist.
        """
        obj = context.active_object
        vg = obj.vertex_groups.get("TopoFit_Landmarks")
        if not vg:
            self.report({'WARNING'}, "No 'TopoFit_Landmarks' vertex group exists to remove from.")
            return {'CANCELLED'}
            
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        weight_layer = bm.verts.layers.deform.active
        if not weight_layer:
            self.report({'INFO'}, "No vertex weights layer found. Nothing to remove.")
            return {'FINISHED'}
            
        removed_count = 0
        for v in bm.verts:
            if v.select:
                if vg.index in v[weight_layer]:
                    del v[weight_layer][vg.index] # Remove weight for this group
                    removed_count += 1
                    
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"Removed {removed_count} vertices from 'TopoFit_Landmarks' group.")
        return {'FINISHED'}

class TOPOFIT_OT_select_landmarks(bpy.types.Operator):
    """
    Selects all vertices belonging to the "TopoFit_Landmarks" vertex group
    on the active mesh in Edit Mode.
    """
    bl_idname = "topofit.select_landmarks"
    bl_label = "Select Landmarks"
    bl_description = "Selects all vertices assigned to the 'TopoFit_Landmarks' vertex group."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh object in Edit Mode.
        """
        return (context.mode == 'EDIT_MESH' and context.active_object and context.active_object.type == 'MESH')

    def execute(self, context):
        """
        Executes the operator to select all landmark vertices.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success, {'CANCELLED'} if no landmarks are found.
        """
        obj = context.active_object
        indices = get_landmark_indices(obj)
        if not indices:
            self.report({'WARNING'}, "No landmark vertices found in 'TopoFit_Landmarks' group to select.")
            return {'CANCELLED'}
        
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        # Deselect all vertices first
        for v in bm.verts:
            v.select = False
        
        # Select only landmark vertices
        for idx in indices:
            if idx < len(bm.verts): # Safety check for index validity
                bm.verts[idx].select = True
        
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"Selected {len(indices)} landmark vertices.")
        return {'FINISHED'}

class TOPOFIT_OT_toggle_landmark_mask(bpy.types.Operator):
    """
    Toggles a Mask modifier that isolates landmark vertices in the viewport.
    This helps in precisely manipulating landmarks without visual clutter.
    """
    bl_idname = "topofit.toggle_landmark_mask"
    bl_label = "Toggle Landmark Mask"
    bl_description = "Toggles a Mask modifier to isolate/show only landmark vertices in the viewport."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh object that has
        the "TopoFit_Landmarks" vertex group.
        """
        obj = context.active_object
        return (obj and obj.type == 'MESH' and "TopoFit_Landmarks" in obj.vertex_groups)

    def execute(self, context):
        """
        Executes the operator to toggle the landmark mask modifier.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success.
        """
        obj = context.active_object
        mask_mod = obj.modifiers.get("TopoFit_Landmark_Mask")
        
        if mask_mod:
            obj.modifiers.remove(mask_mod)
            self.report({'INFO'}, "Mask modifier removed. Showing all vertices.")
        else:
            vg = obj.vertex_groups.get("TopoFit_Landmarks")
            # The poll method ensures the group exists, but create it here as fallback if somehow missing
            if not vg:
                vg = obj.vertex_groups.new(name="TopoFit_Landmarks")
            
            mask_mod = obj.modifiers.new(name="TopoFit_Landmark_Mask", type='MASK')
            mask_mod.vertex_group = "TopoFit_Landmarks"
            mask_mod.show_on_cage = True
            mask_mod.show_in_editmode = True
            self.report({'INFO'}, "Mask modifier applied. Landmark vertices isolated.")
        return {'FINISHED'}

class TOPOFIT_OT_refresh_mirror_map(bpy.types.Operator):
    """
    Regenerates the mirror map for the active mesh based on its current geometry.
    This is useful if the topology has changed significantly.
    """
    bl_idname = "topofit.refresh_mirror_map"
    bl_label = "Refresh Mirror Map"
    bl_description = "Recalculates symmetrical vertex pairs for the active mesh. Use if topology changes."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh object.
        """
        obj = context.active_object
        return obj and obj.type == 'MESH'

    def execute(self, context):
        """
        Executes the operator to regenerate the mirror map.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success.
        """
        obj = context.active_object
        mirror_map, midline_verts = generate_mirror_map(obj.data.vertices)
        store_mirror_data(obj.data, mirror_map, midline_verts)
        pairs = len(mirror_map) // 2
        invalidate_distance_cache(obj.name)
        self.report({'INFO'}, f"Mirror map rebuilt: {pairs} pairs, {len(midline_verts)} midline. Geodesic distance cache invalidated.")
        return {'FINISHED'}

class TOPOFIT_OT_revert_to_basis(bpy.types.Operator):
    """
    For each selected vertex, copies its position from the 'Basis' shape key
    into the active shape key, effectively resetting its deformation.
    """
    bl_idname = "topofit.revert_to_basis"
    bl_label = "Revert Selected to Basis"
    bl_description = "Resets selected vertices in the active shape key back to their 'Basis' positions."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh in Edit Mode,
        with shape keys, and the active shape key is not 'Basis'.
        """
        obj = context.active_object
        return (obj and obj.mode == 'EDIT' and obj.type == 'MESH' and
                obj.data.shape_keys is not None and "Basis" in obj.data.shape_keys.key_blocks and
                obj.active_shape_key_index != 0)

    def execute(self, context):
        """
        Executes the operator to revert selected vertices.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success, {'CANCELLED'} if shape key layers are inaccessible.
        """
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        active_key = obj.active_shape_key
        basis_key = obj.data.shape_keys.key_blocks["Basis"]
        
        shape_layer = bm.verts.layers.shape.get(active_key.name)
        basis_layer = bm.verts.layers.shape.get(basis_key.name)
        
        if not shape_layer or not basis_layer:
            self.report({'ERROR'}, "Could not access shape key layers in BMesh. Ensure 'Basis' and active shape key exist.")
            return {'CANCELLED'}
            
        reverted_count = 0
        for v in bm.verts:
            if v.select:
                v[shape_layer] = v[basis_layer].copy()
                v.co = v[basis_layer].copy() # Explicitly update live Edit Mode coords
                reverted_count += 1
                
        bmesh.update_edit_mesh(obj.data)
        if context.area:
            context.area.tag_redraw()
        self.report({'INFO'}, f"Reverted {reverted_count} selected vertices to Basis.")
        return {'FINISHED'}

class TOPOFIT_OT_apply_symmetry(bpy.types.Operator):
    """
    Applies symmetry to selected landmark vertices. For each *selected and moved*
    landmark, its displacement from the 'Basis' position is mirrored to its
    symmetrical partner across the X-axis. Compatible with Mask modifiers.
    """
    bl_idname = "topofit.apply_symmetry"
    bl_label = "Apply Symmetry"
    bl_description = "Mirrors displacements of selected landmarks to their symmetrical partners across the X-axis."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        It's available if there is an active mesh in Edit Mode,
        with shape keys, and the active shape key is not 'Basis'.
        """
        obj = context.active_object
        return (obj and obj.mode == 'EDIT' and obj.type == 'MESH' and
                obj.data.shape_keys is not None and "Basis" in obj.data.shape_keys.key_blocks and
                obj.active_shape_key_index != 0)

    def execute(self, context):
        """
        Executes the operator to apply symmetry.

        Args:
            context (bpy.context): The current Blender context.

        Returns:
            set: {'FINISHED'} on success, {'CANCELLED'} on error or if no landmarks are found.
        """
        obj = context.active_object
        
        all_vg_landmark_indices = set(get_landmark_indices(obj))
        if not all_vg_landmark_indices:
            self.report({'ERROR'}, "No vertices assigned to 'TopoFit_Landmarks' group. Add some first.")
            return {'CANCELLED'}

        # Temporarily disable Mask modifier for accurate calculations if active
        mask_mod = obj.modifiers.get("TopoFit_Landmark_Mask")
        mask_was_active = False
        if mask_mod:
            mask_was_active = True
            mask_mod.show_in_editmode = False
            mask_mod.show_on_cage = False
            obj.update_tag() # Force dependency graph update
            context.view_layer.update() # Force viewport redraw

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        active_key = obj.active_shape_key
        basis_key = obj.data.shape_keys.key_blocks["Basis"]
        
        shape_layer = bm.verts.layers.shape.get(active_key.name)
        basis_layer = bm.verts.layers.shape.get(basis_key.name)
        
        if not shape_layer or not basis_layer:
            self.report({'ERROR'}, "Could not access shape key layers. Ensure 'Basis' and active shape key exist.")
            if mask_was_active and mask_mod:
                mask_mod.show_in_editmode = True
                mask_mod.show_on_cage = True
            return {'CANCELLED'}
            
        mirror_map, _midline = load_mirror_map(obj.data)
        if not mirror_map:
            self.report({'INFO'}, "Mirror map not found. Generating now...")
            mirror_map, midline_verts = generate_mirror_map(obj.data.vertices)
            store_mirror_data(obj.data, mirror_map, midline_verts)
            
        selected_landmark_indices = {v.index for v in bm.verts if v.select and v.index in all_vg_landmark_indices}
        
        if not selected_landmark_indices:
            self.report({'INFO'}, "No selected landmark vertices found. Select landmarks to apply symmetry.")
            if mask_was_active and mask_mod:
                mask_mod.show_in_editmode = True
                mask_mod.show_on_cage = True
            return {'FINISHED'}

        # Capture current live vertex coordinates for all potentially affected landmarks (selected + partners)
        current_live_positions = {}
        for idx in all_vg_landmark_indices: # Iterate over ALL landmarks in the group
             v = bm.verts[idx]
             current_live_positions[idx] = v.co.copy()


        positions_to_update = {} # Stores final positions for all affected landmarks (selected + partners)
        
        for idx in selected_landmark_indices:
            v = bm.verts[idx]
            current_pos = current_live_positions[idx] # Use the captured current_live_positions for delta calculation
            basis_pos = v[basis_layer]
            delta = current_pos - basis_pos # Displacement from basis
            
            # Store the current position of the source landmark for update
            positions_to_update[idx] = current_pos.copy() 

            # If the source landmark has moved significantly, calculate its partner's new position
            if delta.length > 1e-6:
                partner_idx = mirror_map.get(v.index)
                if partner_idx is not None:
                    partner_v_in_bm = bm.verts[partner_idx]
                    mirrored_delta = Vector((-delta.x, delta.y, delta.z)) # Mirror X-axis displacement
                    
                    partner_basis = partner_v_in_bm[basis_layer] 
                    new_partner_pos = partner_basis + mirrored_delta
                    positions_to_update[partner_idx] = new_partner_pos
        
        if not positions_to_update:
            self.report({'INFO'}, "No significant changes to selected landmarks or their partners to mirror.")
            if mask_was_active and mask_mod:
                mask_mod.show_in_editmode = True
                mask_mod.show_on_cage = True
            return {'FINISHED'}
            
        # Apply all calculated final positions to both shape layers and live viewport coordinates
        for idx, new_pos in positions_to_update.items():
            v = bm.verts[idx]
            v[shape_layer] = new_pos # Update shape layer data
            v.co = new_pos           # Update live viewport coordinate

        bm.normal_update()
        bm.select_flush(True) # Update internal selection state
        bmesh.update_edit_mesh(obj.data) # Push BMesh changes to Mesh
        obj.data.update() # Ensure Mesh data updates (e.g., bounding box)

        if context.area:
            context.area.tag_redraw() # Request viewport redraw
            
        # Re-enable mask if it was active
        if mask_was_active and mask_mod:
            mask_mod.show_in_editmode = True
            mask_mod.show_on_cage = True
            obj.update_tag()
            context.view_layer.update() # Force viewport update after re-enabling mask
            
        self.report({'INFO'}, f"Symmetry applied to {len(positions_to_update)} landmark vertices (including partners).")
        return {'FINISHED'}

# ---------------------------------------------------------------------------
# GEODESIC IDW DETAIL DEFORMATION (NATIVE EDIT MODE)
# ---------------------------------------------------------------------------

class TOPOFIT_OT_deform_detail_vertices(bpy.types.Operator):
    """
    Deforms all non-landmark vertices in the active shape key using a
    geodesic distance-weighted Inverse Distance Weighting (IDW) algorithm.
    This operator is modal to handle potentially long calculations.
    """
    bl_idname = "topofit.deform_detail_vertices"
    bl_label = "Fit Remaining Mesh (IDW)"
    bl_description = "Smoothly propagates landmark deformations to the rest of the mesh using Inverse Distance Weighting."
    bl_options = {'REGISTER'} # Removed UNDO as modal operators often manage their own undo

    # Properties for falloff power and max influence distance are now in TopoFit_SceneProperties
    # The operator can access them via context.scene.topofit_props

    # Internal state variables for the modal operator
    _timer = None
    _landmark_list = None
    _lm_step = 0
    _all_distances = None
    _adjacency = None
    _landmark_indices = None
    _source_obj = None
    _basis_key_name = None
    _active_key_name = None
    _n_verts = 0
    _cache_hit = False
    _mask_was_active = False # To store if mask was active before disabling

    @classmethod
    def poll(cls, context):
        """
        Determines if the operator can be executed.
        Available if there's an active mesh in Edit Mode, with shape keys,
        active key is not 'Basis', and 'TopoFit_Landmarks' group exists.
        """
        obj = context.active_object
        if not (obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH'):
            return False
        if not obj.data.shape_keys:
            return False
        if obj.active_shape_key_index == 0:
            return False
        return "TopoFit_Landmarks" in obj.vertex_groups
        
    def invoke(self, context, event):
        """
        Invokes the modal operator, setting up initial state and starting the timer.
        """
        wm = context.window_manager
        obj = context.active_object
        scene_props = context.scene.topofit_props

        active_key = obj.active_shape_key
        basis_key = obj.data.shape_keys.key_blocks["Basis"]
        
        landmark_indices = set(get_landmark_indices(obj))
        if not landmark_indices:
            self.report({'ERROR'}, "No vertices in 'TopoFit_Landmarks' group. Cannot fit mesh.")
            return {'CANCELLED'}
            
        # Temporarily disable Mask modifier for full mesh calculation
        mask_mod = obj.modifiers.get("TopoFit_Landmark_Mask")
        self._mask_was_active = False
        if mask_mod:
            self._mask_was_active = True
            mask_mod.show_in_editmode = False
            mask_mod.show_on_cage = False
            obj.update_tag()
            context.view_layer.update()

        # Check for cached distances
        distances, adjacency, cache_hit = get_cached_distances(obj.name, obj, landmark_indices)
        n_landmarks = len(landmark_indices)
        
        if cache_hit:
            context.area.header_text_set("Deforming detail vertices -- applying cached distances...")
            self._all_distances = defaultdict(dict)
            max_d = scene_props.topofit_max_influence_distance # Access from scene properties
            for lm_idx, lm_dists in distances.items():
                for v, d in lm_dists.items():
                    if not max_d or d <= max_d:
                        self._all_distances[v][lm_idx] = d
        else:
            context.area.header_text_set(f"Deforming detail vertices -- computing geodesic distances 0/{n_landmarks} (0%)")
            self._all_distances = defaultdict(dict)
            adjacency = build_adjacency(obj.data) # Recalculate adjacency if cache miss
        
        self._source_obj = obj
        self._basis_key_name = basis_key.name
        self._active_key_name = active_key.name
        self._landmark_indices = landmark_indices
        self._landmark_list = list(landmark_indices)
        self._n_verts = len(obj.data.vertices)
        self._adjacency = adjacency
        self._all_distances = self._all_distances # Ensure this is properly initialized after cache logic
        self._cache_hit = cache_hit
        # Start iteration from 0 if cache miss, otherwise jump to finish
        self._lm_step = n_landmarks if cache_hit else 0 
        
        # Add a timer to call modal() periodically
        self._timer = wm.event_timer_add(0.01, window=context.window) # Small delay to keep UI responsive
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}
        
    def modal(self, context, event):
        """
        Modal function called repeatedly by the timer to compute geodesic distances.
        This allows the UI to remain responsive during heavy calculations.
        """
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}\

        scene_props = context.scene.topofit_props # Get scene properties in modal
        n_landmarks = len(self._landmark_list)
        if self._lm_step >= n_landmarks:
            # All distances calculated, proceed to finish
            return self._finish(context)
        
        lm_idx = self._landmark_list[self._lm_step]
        max_d = scene_props.topofit_max_influence_distance # Access from scene properties
        
        dist = {lm_idx: 0.0}
        heap = [(0.0, lm_idx)] # Min-heap for Dijkstra's algorithm

        # Dijkstra's algorithm for geodesic distances from current landmark
        while heap:
            d, v = heapq.heappop(heap)
            if d > dist.get(v, float('inf')):\
                continue
            if max_d and d > max_d: # Stop if max influence distance exceeded
                continue
            
            for nb, edge_len in self._adjacency.get(v, []):
                nd = d + edge_len
                if max_d and nd > max_d:
                    continue
                if nd < dist.get(nb, float('inf')):
                    dist[nb] = nd
                    heapq.heappush(heap, (nd, nb))
                    
        # Store distances from this landmark to non-landmark vertices, excluding self (d > 0.0)
        detail_dists = {v: d for v, d in dist.items() if v not in self._landmark_indices and d > 0.0}
        for v, d in detail_dists.items():
            if not max_d or d <= max_d:
                self._all_distances[v][lm_idx] = d
            
        obj_name = context.active_object.name
        # Store computed distances for this landmark in the global cache
        if obj_name not in _distance_cache:
            _distance_cache[obj_name] = {\
                'mesh_ptr': id(self._source_obj.data), # Use ID for robust mesh data change detection
                'landmark_indices': frozenset(self._landmark_indices),
                'adjacency': self._adjacency,
                'distances': {}
            }
        _distance_cache[obj_name]['distances'][lm_idx] = detail_dists
        
        self._lm_step += 1
        pct = int(100 * self._lm_step / n_landmarks)
        context.area.header_text_set(f"Deforming detail vertices -- computing geodesic distances {self._lm_step}/{n_landmarks} ({pct}%)")
        
        return {'RUNNING_MODAL'}
        
    def _finish(self, context):
        """
        Finalizes the deformation process once all distances are computed.\
        """
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        context.area.header_text_set(None) # Clear header text
        
        obj = self._source_obj
        scene_props = context.scene.topofit_props # Get scene properties in finish
        
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        shape_layer = bm.verts.layers.shape.get(self._active_key_name)
        basis_layer = bm.verts.layers.shape.get(self._basis_key_name)
        
        landmark_indices = self._landmark_indices
        all_distances = self._all_distances
        
        # Ensure live viewport changes on landmarks are committed to the shape layer
        # before calculating their deltas for IDW.
        for idx in landmark_indices:
            bm.verts[idx][shape_layer] = bm.verts[idx].co.copy()
        
        # Calculate displacement deltas for all landmarks
        landmark_deltas = {idx: bm.verts[idx][shape_layer] - bm.verts[idx][basis_layer] for idx in landmark_indices}
        zero_vec = Vector((0.0, 0.0, 0.0))
        moved = 0
        reset = 0
        
        # Apply Inverse Distance Weighting to non-landmark vertices
        for v in bm.verts:
            v_idx = v.index
            if v_idx in landmark_indices:
                continue # Skip landmarks, their positions are fixed by user
            
            dist_map = all_distances.get(v_idx)
            if not dist_map:
                # If a vertex is outside influence distance or has no landmarks influencing it,\
                # reset it to its basis position.
                v[shape_layer] = v[basis_layer].copy()
                v.co = v[basis_layer].copy()
                reset += 1
                continue
                
            # Use falloff_power from scene properties
            falloff_power = scene_props.topofit_falloff_power
            raw_weights = {lm: 1.0 / (d ** falloff_power) for lm, d in dist_map.items()}
            total_w = sum(raw_weights.values())
            
            blended_delta = zero_vec.copy()
            for lm_idx, w in raw_weights.items(): 
                blended_delta += (w / total_w) * landmark_deltas[lm_idx]
                
            v[shape_layer] = v[basis_layer] + blended_delta
            v.co = v[basis_layer] + blended_delta
            moved += 1
            
        bm.normal_update() # Update vertex normals if topology changed (not in this case, but good practice)
        # bmesh.select_flush(True) # Not strictly needed here, but doesn't hurt.
        bmesh.update_edit_mesh(obj.data) # Push BMesh changes to the actual mesh
        obj.data.update() # Update ID properties (e.g., bounding box)
        
        if context.area:
            context.area.tag_redraw() # Request viewport redraw
        
        bpy.ops.ed.undo_push(message="TopoFit: Deform Mesh (IDW)") # Add to Undo history
        self.report({'INFO'}, f"Fitting complete: {moved} vertices deformed, {reset} reset to Basis, {len(landmark_indices)} landmarks unchanged.")

        # Re-enable mask if it was active
        if self._mask_was_active and self._source_obj.modifiers.get("TopoFit_Landmark_Mask"):
            self._source_obj.modifiers["TopoFit_Landmark_Mask"].show_in_editmode = True
            self._source_obj.modifiers["TopoFit_Landmark_Mask"].show_on_cage = True
            self._source_obj.update_tag()
            context.view_layer.update()

        return {'FINISHED'}