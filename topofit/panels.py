"""
This module defines the UI panel for the TopoFit Blender Addon.

It organizes the addon's operators and properties into a logical workflow
within Blender's 3D Viewport sidebar, providing dynamic guidance and status
information to the user.
"""

import bpy
from .utils import (
    get_topofit_status, get_landmark_indices, load_mirror_map,
    STATUS_OK,
    ERROR_NO_ACTIVE_MESH,
    ERROR_NO_SHAPEKEYS,
    ERROR_BASIS_ACTIVE,
    ERROR_NO_LANDMARKS_GROUP
)
from .operators import ( # Import operators to reference their bl_idname
    TOPOFIT_OT_show_help, TOPOFIT_OT_create_target_key, TOPOFIT_OT_select_mirrored,
    TOPOFIT_OT_add_to_landmarks, TOPOFIT_OT_remove_from_landmarks,
    TOPOFIT_OT_select_landmarks, TOPOFIT_OT_toggle_landmark_mask,
    TOPOFIT_OT_refresh_mirror_map, TOPOFIT_OT_revert_to_basis,
    TOPOFIT_OT_apply_symmetry, TOPOFIT_OT_deform_detail_vertices
)

# ---------------------------------------------------------------------------
# UI PANEL (EDIT MODE DESIGNED)
# ---------------------------------------------------------------------------
class TOPOFIT_PT_panel(bpy.types.Panel):
    """
    The main UI panel for the TopoFit addon, located in the 3D Viewport sidebar.
    It guides the user through the addon's workflow and exposes its functionalities.
    """
    bl_label="TopoFit"
    bl_idname="OBJECT_PT_topofit"
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='TopoFit'

    def draw(self, context):
        """
        Draws the UI elements of the panel.

        Args:
            context (bpy.context): The current Blender context.
        """
        layout = self.layout
        obj = context.active_object
        scene = context.scene
        scene_props = scene.topofit_props # Access custom scene properties
        is_edit = (context.mode == 'EDIT_MESH' and obj is not None and obj.type == 'MESH')
        has_selection = is_edit and obj.data.total_vert_sel > 0
        
        # --- UI LAYOUT SECTIONS (Landmark Setup, Landmark Editing, Mesh Fitting) ---
        col = layout.column(align=True)
        col.label(text="Landmark Setup:")
        row = col.row()
        row.enabled = is_edit
        row.operator(TOPOFIT_OT_select_mirrored.bl_idname)
        row = col.row()
        row.enabled = is_edit
        row.operator(TOPOFIT_OT_select_landmarks.bl_idname)
        row = col.row()
        row.enabled = has_selection
        row.operator(TOPOFIT_OT_add_to_landmarks.bl_idname)
        row = col.row()
        row.enabled = has_selection
        row.operator(TOPOFIT_OT_remove_from_landmarks.bl_idname)
        
        # SAFELY DETERMINE SHAPE KEY STATE BOOLEANS
        has_shapekeys_for_ops = obj is not None and obj.type == 'MESH' and obj.data.shape_keys is not None
        is_not_basis_for_ops = has_shapekeys_for_ops and obj.active_shape_key_index != 0
        
        layout.separator()
        col = layout.column(align=True)
        col.label(text="Landmark Editing:")
        col.operator(TOPOFIT_OT_toggle_landmark_mask.bl_idname)
        row = col.row()
        row.enabled = is_edit and is_not_basis_for_ops
        row.operator(TOPOFIT_OT_revert_to_basis.bl_idname)
        row = col.row()
        row.enabled = is_edit and is_not_basis_for_ops
        row.operator(TOPOFIT_OT_apply_symmetry.bl_idname)
        row = col.row()
        row.enabled = is_edit
        row.operator(TOPOFIT_OT_refresh_mirror_map.bl_idname)
        
        layout.separator()
        col = layout.column(align=True)
        col.label(text="Mesh Fitting:")
        row = col.row()
        row.enabled = is_edit and is_not_basis_for_ops
        row.operator(TOPOFIT_OT_deform_detail_vertices.bl_idname)
        
        # --- COMBINED STATUS & GUIDANCE SECTION (at the bottom, collapsible) ---
        box_status_guidance = layout.box()
        row_status_guidance = box_status_guidance.row(align=True)
        
        # Toggle button for status & guidance
        row_status_guidance.prop(scene_props, "topofit_show_status_guidance",
                                 text="Status & Workflow Guidance",
                                 emboss=False,
                                 icon='TRIA_DOWN' if scene_props.topofit_show_status_guidance else 'TRIA_RIGHT')
        
        if scene_props.topofit_show_status_guidance:
            col_content = box_status_guidance.column(align=True)
            
            # --- START: Integrated CENTRAL EDIT MODE STATE-MACHINE BANNER logic ---
            if obj is None:
                col_content.label(text="❌ No Active Mesh Selected", icon='RESTRICT_SELECT_OFF')
                col_content.label(text="Please select your figure mesh to begin.")
                
            elif obj.type != 'MESH':
                col_content.label(text="❌ Selection is not a Mesh", icon='ERROR')
                col_content.label(text=f"Selected object '{obj.name}' is a {obj.type}. Select a Mesh.")
                
            else:
                landmark_indices = get_landmark_indices(obj)
                has_landmarks = len(landmark_indices) > 0
                has_shapekeys = obj.data.shape_keys is not None
                is_basis_active = has_shapekeys and obj.active_shape_key_index == 0
                
                if is_edit:
                    if not has_landmarks:
                        col_content.label(text="🧬 Step 1: Designate Landmarks", icon='EDITMODE_HLT')
                        col_content.label(text="Select vertices on standard features, click 'Add Selected'.")
                    
                    elif not has_shapekeys or is_basis_active:
                        col_content.label(text="⚠️ Step 2: Set Active Shape Key", icon='SHAPEKEY_DATA')
                        col_content.label(text="You cannot reshape on the Basis key!")
                        col_content.separator()
                        col_content.operator(TOPOFIT_OT_create_target_key.bl_idname, text="Create & Set Reshape Key", icon='ADD')
                        
                    else:
                        col_content.label(text="🔧 Step 3: Align Landmarks & Fit Mesh", icon='SNAP_GRID')
                        col_content.label(text="Move landmarks, use 'Toggle Mask' to isolate, click 'Fit Mesh'.")
                else: # User is in Object Mode
                    if not has_landmarks:
                        col_content.label(text="🧬 Step 1: Designate Landmarks", icon='EDITMODE_HLT')
                        col_content.label(text="👉 Tab into EDIT MODE to select vertices and click 'Add Selected'.")
                    elif not has_shapekeys or is_basis_active:
                        col_content.label(text="⚠️ Step 2: Set Active Shape Key", icon='SHAPEKEY_DATA')
                        col_content.label(text="👉 Tab into EDIT MODE to create or select a target shape key.")
                    else:
                        col_content.label(text="🧘 Safe to Pause / Resume", icon='WORLD')
                        col_content.label(text="All landmarks and shape edits are safely saved.")
                        col_content.label(text="👉 Tab back into EDIT MODE to resume fitting your mesh.")
            # --- END: Integrated CENTRAL EDIT MODE STATE-MACHINE BANNER logic ---
            
            col_content.separator() # Separator between guidance and detailed status
            col_content.label(text="Detailed Status:", icon='INFO') # New heading for detailed status

            # --- START: Original STATUS PANEL INFO logic ---
            status_result, status_obj = get_topofit_status(context)
            
            if status_result == ERROR_NO_ACTIVE_MESH: 
                col_content.label(text="Select an active mesh", icon='RESTRICT_SELECT_OFF')
            elif status_result == ERROR_NO_SHAPEKEYS: 
                col_content.label(text=f"'{status_obj.name}' has no shape keys.", icon='ERROR')
            elif status_result == ERROR_BASIS_ACTIVE:
                col_content.label(text=f"Mesh: {status_obj.name}", icon='OBJECT_DATA')
                col_content.label(text="Select a non-Basis shape key", icon='SHAPEKEY_DATA')
            elif status_result == ERROR_NO_LANDMARKS_GROUP:
                col_content.label(text=f"Mesh: {status_obj.name}", icon='OBJECT_DATA')
                col_content.label(text="Add some vertices to 'TopoFit_Landmarks' group", icon='ERROR')
            elif status_result == STATUS_OK:
                active_sk = status_obj.data.shape_keys.key_blocks[status_obj.active_shape_key_index]
                col_content.label(text=f"Mesh: {status_obj.name}", icon='OBJECT_DATA')
                col_content.label(text=f"Target key: {active_sk.name}", icon='CHECKMARK')
                mirror_map, midline = load_mirror_map(status_obj.data)
                pairs = len(mirror_map) // 2
                total_landmarks = len(get_landmark_indices(status_obj)) # Recalculate landmarks
                col_content.label(text=f"Landmarks: {total_landmarks} total, {pairs} mirrored, {len(midline)} midline", icon='MOD_MIRROR')

            col_content.separator()
            col_content.operator(TOPOFIT_OT_show_help.bl_idname, text="Help", icon='QUESTION')
            # --- END: Original STATUS PANEL INFO logic ---

        # Removed layout.separator() here to reduce vertical space between status/guidance and settings

        # --- SETTINGS / CONFIGURATION SECTION (at the very bottom, collapsible) ---
        box_config = layout.box()
        row_config = box_config.row(align=True)
        # Toggle button for settings
        row_config.prop(scene_props, "topofit_show_settings",
                        text="Settings",
                        emboss=False,
                        icon='TRIA_DOWN' if scene_props.topofit_show_settings else 'TRIA_RIGHT')

        if scene_props.topofit_show_settings:
            col_config = box_config.column(align=True)
            col_config.prop(scene_props, "topofit_auto_create_key", text="Auto-Create Key")
            col_config.prop(scene_props, "topofit_target_key_name", text="Key Name")
            # Expose falloff power and max influence distance from scene properties
            col_config.prop(scene_props, "topofit_falloff_power", text="Falloff Power")
            col_config.prop(scene_props, "topofit_max_influence_distance", text="Max Influence Distance")
