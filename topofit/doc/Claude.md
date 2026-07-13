# 🧬 TopoFit Addon

An elegant, single-mesh landmark-guided shape deformation tool built for Blender. It is designed to fit a standard human figure base topology to high-resolution human scan data.

---

## 🛠️ Project Stack & Technologies

*   **Host Platform:** Blender 3D Viewport Addon (built for Blender 3.0.0+ / Python 3.10+).
*   **API Frameworks:** Blender Python API (`bpy`), low-level Edit Mode mesh manipulation (`bmesh`), and fast structural KD-Trees (`mathutils.kdtree`).
*   **Landmark Storage:** Standard vertex groups targeting a specific group named `"TopoFit_Landmarks"`.
*   **Deformation Database:** Native Blender Shape Keys (editing is strictly blocked on the "Basis" key).
*   **Fitting Math:** Sparse landmark coordinates are interpolated across the rest of the body using geodesic-distance-weighted Inverse Distance Weighting (IDW).

---

## 🗺️ Single-Mesh Fitting Workflow State-Machine

The addon is designed to run **100% natively in Edit Mode** for a seamless, stutter-free viewport experience. The UI panel implements a guide banner that moves the user through these sequential phases:

1.  **Step 1: Designate Landmarks**
    *   *Goal:* Define anatomical features (eyes, nose, joints, fingertips).
    *   *Action:* User selects vertices and clicks **"Add Selected to Landmarks"**. This assigns vertices to the `"TopoFit_Landmarks"` vertex group.
2.  **Step 2: Set Target Shape Key**
    *   *Goal:* Protect baseline geometry from accidental destruction.
    *   *Action:* User selects or adds a non-Basis shape key (e.g. `"TopoFit_Target"`) in the native Blender panel. The plugin also provides an "Auto-Create Key" option in settings for 1-click setup.
3.  **Step 3: Align Landmarks & Symmetrize**
    *   *Goal:* Position landmarks to match scan data.
    *   *Action:* User isolates landmark vertices using the **"Toggle Landmark Mask"** (utilizing a temporary `MASK` modifier), drags them to the scan, and mirrors edits using the **"Apply Symmetry"** operator.
4.  **Step 4: Fit Remaining Mesh**
    *   *Goal:* Interpolate body deformations.
    *   *Action:* User runs the **"Fit Remaining Mesh"** operator to calculate and apply geodesic-based IDW displacement.

---

## ⚠️ Critical Development Rules & Guardrails

When editing this codebase, **always adhere to the following architectural patterns:**

### 1. Viewport & Shape Key Synchronicity (The Golden Rule)
Because the addon operates inside Edit Mode, updating shape key coordinates in the database layer (`bm.verts[idx][shape_layer]`) is **not enough** to update what is displayed on screen.
*   **You must update both:** You must explicitly assign coordinates to both the shape layer *and* the active Edit Mode coordinate variable:
    ```python
    bm.verts[idx][shape_layer] = new_pos
    bm.verts[idx].co = new_pos
    ```
*   **Always Flush and Redraw:** After modifying mesh data, trigger viewport refreshes using:
    ```python
    bm.normal_update()
    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)
    obj.data.update()
    # Safely redraw only if context.area exists (not in headless/CLI mode)
    if context.area:
        context.area.tag_redraw()
    ```

### 2. Guarding Hidden Vertices (Masks)
When a user isolates landmarks using the **Toggle Landmark Mask** operator, hidden vertices are excluded from typical Edit Mode BMesh selection and update loops.
*   **Toggle modifiers for write-access:** Operators modifying hidden vertices (such as `Apply Symmetry` or `Fit Mesh`) must temporarily toggle the mask visibility to `False` to prevent viewport updates from blocking the data write:
    ```python
    mask_mod = obj.modifiers.get("TopoFit_Landmark_Mask")
    if mask_mod:
        mask_mod.show_in_editmode = False
        # ... perform work ...
        mask_mod.show_in_editmode = True
    ```

### 3. Native BMesh Vertex Group Calculations
To avoid Blender synchronization delays, helper functions should read active weights directly from the live BMesh deform layer when the mesh is in Edit Mode:
    ```python
    bm = bmesh.from_edit_mesh(obj.data)
    weight_layer = bm.verts.layers.deform.active
    # Evaluate weight_layer[group_index] directly...
    ```

### 4. Preservation of Blender Context
*   Avoid using `bpy.ops` inside loop calculations. Use raw data layers (`BMesh` API) instead. This keeps operators fast, stable, and completely context-independent.