import bpy
import bmesh
from mathutils import Vector
import traceback
import sys
import os

# --- CRITICAL FIX START: Ensure addon can be imported and registered directly ---
# Add the directory containing the 'topofit' addon to Python's path
# This assumes test_topofit.py is in the parent directory of 'topofit/'
addon_parent_dir = os.path.dirname(os.path.abspath(__file__))
if addon_parent_dir not in sys.path:
    sys.path.insert(0, addon_parent_dir)

# Now, directly import the addon's __init__ module and call its register function
try:
    # Import the main addon module
    import topofit
    # Call its register function to make operators and properties available
    topofit.register()
    print("INFO: TopoFit addon directly registered for testing.")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to directly register TopoFit addon. Error: {e}")
    sys.exit(1) # Exit if essential registration fails
# --- CRITICAL FIX END ---

# CRITICAL FIX: Import utility functions from the addon's utils module
# This import will now definitely work because topofit is in sys.path and registered
try:
    from topofit.utils import load_mirror_map
except ImportError as e:
    print(f"ERROR: Failed to import load_mirror_map from topofit.utils after direct registration. Error: {e}")
    sys.exit(1)


def run_tests():
    print("\n" + "="*50)
    print("STARTING TOPOFIT SPHERE DEFORMATION TESTS")
    print("="*50)

    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    def run_single_test(test_func, test_name):
        nonlocal total_tests, passed_tests, failed_tests
        total_tests += 1
        print(f"\n--- Running: {test_name} ---")
        try:
            test_func()
            print(f"PASSED: {test_name}")
            passed_tests += 1
        except AssertionError as e:
            print(f"FAILED: {test_name} - {e}")
            failed_tests += 1
        except Exception as e:
            print(f"ERROR: {test_name} - An unexpected exception occurred: {e}")
            traceback.print_exc() # Print full traceback for unexpected errors
            failed_tests += 1

    # -----------------------------------------------------------------------
    # Test Setup Function
    # -----------------------------------------------------------------------
    def setup_scene():
        # Clear existing geometry
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        
        bpy.ops.object.select_all(action='SELECT')
        if bpy.context.selected_objects:
            bpy.ops.object.delete(use_global=False)
        print("INFO: Workspace cleared. Deleting all scene objects.")

        # Create Suzanne (Monkey) for general tests
        bpy.ops.mesh.primitive_monkey_add(size=2.0, location=(0, 0, 0))
        obj = bpy.context.active_object
        obj.name = "Test_Suzanne"
        print(f"INFO: Created test mesh '{obj.name}' with {len(obj.data.vertices)} vertices.")
        
        # We no longer need to call bpy.ops.preferences.addon_enable(module="topofit")
        # because topofit.register() was called directly at the script's start.

        # Ensure the scene's TopoFit config is default
        # This will now work because topofit.register() was called earlier
        bpy.context.scene.topofit_props.topofit_auto_create_key = True
        bpy.context.scene.topofit_props.topofit_target_key_name = "TopoFit_Target"

        return obj

    # -----------------------------------------------------------------------
    # TEST SEQUENCE START
    # -----------------------------------------------------------------------

    # Global variables to pass data between tests
    obj = None
    bm = None
    test_v_idx = -1
    x1_idx = -1
    x_neg1_idx = -1
    mirror_map = None

    # Test 1: Full setup with TopoFit specific keys
    def test_initial_setup():
        nonlocal obj
        obj = setup_scene()
        assert obj is not None, "Setup failed to create Suzanne."
        
        # Verify TopoFit properties exist after direct registration
        assert hasattr(bpy.context.scene, 'topofit_props'), "bpy.context.scene has no 'topofit_props' after registration."
        assert hasattr(bpy.context.scene.topofit_props, 'topofit_auto_create_key'), "topofit_auto_create_key property missing."
    run_single_test(test_initial_setup, "Setup Scene and Initialize TopoFit Addon")

    # Only run further tests if initial setup passed
    if obj is None:
        print("Skipping further tests due to initial setup failure.")
    else:
        # Test 2: Create TopoFit Target Shape Key via Auto-Create on Add Landmark
        def test_create_shape_key_via_add_landmark():
            nonlocal bm, test_v_idx
            
            bpy.ops.object.mode_set(mode='EDIT')
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()

            # Select a vertex (e.g., index 0)
            test_v_idx = 0
            for v in bm.verts: v.select = False # Deselect all
            bm.verts[test_v_idx].select = True
            bmesh.update_edit_mesh(obj.data)

            # Running add_to_landmarks will now trigger auto-create_target_key due to default config
            res = bpy.ops.topofit.add_to_landmarks()
            assert res == {'FINISHED'}, "Add to landmarks operator failed."

            # Re-fetch BMesh and layers after operator call
            bm = bmesh.from_edit_mesh(obj.data) # CRITICAL: Re-fetch BMesh
            bm.verts.ensure_lookup_table()
            
            # Verify shape keys were created and activated correctly
            assert obj.data.shape_keys is not None, "Shape keys were not initialized."
            assert len(obj.data.shape_keys.key_blocks) >= 2, "Expected at least 'Basis' and 'TopoFit_Target' keys."
            assert obj.active_shape_key_index == obj.data.shape_keys.key_blocks.find("TopoFit_Target"), "TopoFit_Target shape key is not active."
            
            # Re-fetch references for local use (no nonlocal needed here as they are reassigned)
            vg = obj.vertex_groups.get("TopoFit_Landmarks")
            weight_layer = bm.verts.layers.deform.active

            assert vg is not None, "'TopoFit_Landmarks' vertex group missing."
            assert weight_layer is not None, "Active weight/deform layer not found."
            
            test_v_re = bm.verts[test_v_idx]
            assert vg.index in test_v_re[weight_layer] and test_v_re[weight_layer][vg.index] == 1.0, f"Vertex {test_v_idx} not added to landmarks group."
            print(f"INFO: Success: Vert index {test_v_idx} assigned, TopoFit_Target key created/activated.")
        run_single_test(test_create_shape_key_via_add_landmark, "Auto-Create Target Key & Add Landmark")

        # Test 3: Toggle Mask Modifier
        def test_toggle_mask():
            nonlocal bm # Need to update bm if it's referenced later
            bm = bmesh.from_edit_mesh(obj.data) # Re-fetch bm as it might have been freed by previous ops
            bm.verts.ensure_lookup_table()

            assert "TopoFit_Landmark_Mask" not in obj.modifiers, "Mask should not exist initially."
            bpy.ops.topofit.toggle_landmark_mask()
            assert "TopoFit_Landmark_Mask" in obj.modifiers, "Mask was not added."
            assert obj.modifiers["TopoFit_Landmark_Mask"].type == 'MASK', "Modifier is not of type MASK."
            bpy.ops.topofit.toggle_landmark_mask()
            assert "TopoFit_Landmark_Mask" not in obj.modifiers, "Mask was not removed on toggle."
            print("INFO: Isolated landmark MASK modifier toggled on and off cleanly.")
        run_single_test(test_toggle_mask, "Toggle Landmark Mask")

        # Test 4: Mirror Map Rebuilding
        def test_mirror_map_rebuilding():
            nonlocal mirror_map
            res = bpy.ops.topofit.refresh_mirror_map()
            assert res == {'FINISHED'}, "Refresh mirror map operator failed."
            assert "mirror_map" in obj.data, "Mirror map metadata was not saved."
            assert "midline_verts" in obj.data, "Midline metadata was not saved."
            mirror_map, _midline = load_mirror_map(obj.data) # Load for later use
            assert mirror_map is not None, "Mirror map did not load correctly."
            print("INFO: Symmetrical mirror map compiled and stored to mesh database.")
        run_single_test(test_mirror_map_rebuilding, "Mirror Map Rebuilding")

        # Test 5: Select Mirrored
        def test_select_mirrored():
            nonlocal x1_idx, x_neg1_idx, bm
            
            bm = bmesh.from_edit_mesh(obj.data) # Re-fetch bm
            bm.verts.ensure_lookup_table()
            
            # Deselect all, select x=1 vertex, then run select_mirrored
            for v in bm.verts: v.select = False
            
            # Find closest to (1,0,0) as our source
            x1_v_orig = min(obj.data.vertices, key=lambda v: (v.co - Vector((1.0, 0.0, 0.0))).length)
            x1_idx = x1_v_orig.index
            bm.verts[x1_idx].select = True
            bmesh.update_edit_mesh(obj.data)

            bpy.ops.topofit.select_mirrored()
            
            bm = bmesh.from_edit_mesh(obj.data) # Re-fetch BMesh after operator
            bm.verts.ensure_lookup_table()

            # Find vertex closest to (-1,0,0) as our expected partner
            x_neg1_v_orig = min(obj.data.vertices, key=lambda v: (v.co - Vector((-1.0, 0.0, 0.0))).length)
            x_neg1_idx = x_neg1_v_orig.index

            assert bm.verts[x_neg1_idx].select, f"Vertex closest to (-1, 0, 0) was not selected by select_mirrored."
            print(f"INFO: Selection mirrored: Symmetrical vertex closest to (-1,0,0) at index {x_neg1_idx} was selected!")

            # Add both to the landmarks group
            bpy.ops.topofit.add_to_landmarks()
            bm = bmesh.from_edit_mesh(obj.data) # Re-fetch after operator
            bm.verts.ensure_lookup_table()
            
            # Re-fetch for local use
            vg = obj.vertex_groups.get("TopoFit_Landmarks")
            weight_layer = bm.verts.layers.deform.active
            
            x1_v_re = bm.verts[x1_idx]
            x_neg1_v_re = bm.verts[x_neg1_idx]
            assert vg.index in x1_v_re[weight_layer] and vg.index in x_neg1_v_re[weight_layer], "Both source and partner not in landmark group."
            print("INFO: Confirmed: Both source and partner landmarks written to group.")
        run_single_test(test_select_mirrored, "Select Mirrored and Add to Landmarks")

        # Test 6: Reversion Safety - Sequence 1 (Move, Apply Symmetry)
        def test_symmetry_pass1():
            nonlocal bm
            # Re-fetch BMesh and vertex references
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            x1_v = bm.verts[x1_idx]
            x_neg1_v = bm.verts[x_neg1_idx]
            
            # Move x1_v
            x1_v.co = Vector((1.5, 0.0, 0.125))
            bmesh.update_edit_mesh(obj.data)
            print(f"INFO: Translated vertex {x1_idx} to coordinate: {x1_v.co}")

            bpy.ops.topofit.apply_symmetry()

            # Re-fetch BMesh and vertex references
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            x1_v = bm.verts[x1_idx] # Update reference
            x_neg1_v = bm.verts[x_neg1_idx] # Update reference
            
            # Verify partner moved
            expected_partner_pos = Vector((-1.5, 0.0, 0.125))
            assert (x_neg1_v.co - expected_partner_pos).length < 1e-4, f"FAIL: Symmetrical partner vertex is at {x_neg1_v.co}, expected {expected_partner_pos}."
            print(f"INFO: Symmetrical partner index {x_neg1_idx} matches perfectly at: {x_neg1_v.co}")
            # Verify source did not revert
            expected_source_pos = Vector((1.5, 0.0, 0.125))
            assert (x1_v.co - expected_source_pos).length < 1e-4, f"FAIL: Source landmark reverted to {x1_v.co}! Expected: {expected_source_pos}"
            print(f"INFO: Source landmark index {x1_idx} remained at: {x1_v.co}")
        run_single_test(test_symmetry_pass1, "Symmetry (Pass 1) & No Reversion")

        # Test 7: Reversion Safety - Sequence 2 (Move further, Apply Symmetry)
        def test_symmetry_pass2_reversion_check():
            nonlocal bm
            # Re-fetch BMesh and vertex references
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            x1_v = bm.verts[x1_idx]
            x_neg1_v = bm.verts[x_neg1_idx]

            # Move x1_v further
            x1_v.co = Vector((1.5, 0.0, -0.125))
            bmesh.update_edit_mesh(obj.data)
            print(f"INFO: Translated vertex {x1_idx} further to coordinate: {x1_v.co}")

            bpy.ops.topofit.apply_symmetry()

            # Re-fetch BMesh and vertex references
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            x1_v = bm.verts[x1_idx] # Update reference
            x_neg1_v = bm.verts[x_neg1_idx] # Update reference

            expected_moved_pos = Vector((1.5, 0.0, -0.125))
            expected_partner_pos = Vector((-1.5, 0.0, -0.125))

            assert (x_neg1_v.co - expected_partner_pos).length < 1e-4, f"FAIL: Symmetrical partner is at {x_neg1_v.co}, expected {expected_partner_pos}."
            assert (x1_v.co - expected_moved_pos).length < 1e-4, f"FAIL: Landmark reverted to {x1_v.co}! Expected: {expected_moved_pos}"
            print(f"INFO: Symmetrical partner index {x_neg1_idx} matches perfectly at: {x_neg1_v.co}")
            print(f"INFO: Landmark index {x1_idx} stayed safely at: {x1_v.co}")
        run_single_test(test_symmetry_pass2_reversion_check, "Symmetry (Pass 2) & Reversion Safety Check")

        # Test 8: Revert Selected to Basis
        def test_revert_to_basis():
            nonlocal bm
            # Re-fetch BMesh and vertex references
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            test_v = bm.verts[x1_idx]
            partner_v = bm.verts[x_neg1_idx]

            test_v.select = True
            partner_v.select = True
            bmesh.update_edit_mesh(obj.data)

            res = bpy.ops.topofit.revert_to_basis()
            assert res == {'FINISHED'}, "Revert to basis operator failed."

            # Re-fetch BMesh reference after revert_to_basis!
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            test_v = bm.verts[x1_idx] # Update reference

            basis_layer = bm.verts.layers.shape.get("Basis")
            assert (test_v.co - test_v[basis_layer]).length < 1e-6, f"Vertex {x1_idx} did not revert to original coordinates (diff: {(test_v.co - test_v[basis_layer]).length})."
            assert (partner_v.co - bm.verts[x_neg1_idx][basis_layer]).length < 1e-6, f"Vertex {x_neg1_idx} did not revert to original coordinates (diff: {(partner_v.co - bm.verts[x_neg1_idx][basis_layer]).length})."
            print("INFO: Displaced landmarks reverted perfectly back to original Basis coordinates.")
        run_single_test(test_revert_to_basis, "Revert Selected to Basis")

    # Clean up and return to Object Mode
    bpy.ops.object.mode_set(mode='OBJECT')

    print("\n" + "="*50)
    print(f"TOPOFIT TEST SUMMARY: {passed_tests}/{total_tests} PASSED, {failed_tests} FAILED")
    print("="*50)

if __name__ == "__main__":
    run_tests()