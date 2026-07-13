# 🤖 AI Agent Guidelines for TopoFit Blender Addon

This document provides essential context, architectural patterns, and development guidelines for any AI agent assisting with the **TopoFit** Blender addon. Please review these instructions thoroughly before making any code modifications or providing advice.

---

## 🧬 Project Overview: TopoFit Blender Addon

**TopoFit** is an elegant, single-mesh landmark-guided shape deformation tool built for Blender. Its primary purpose is to non-destructively fit a standard base topology (e.g., a clean human mesh) to raw, potentially messy, high-resolution scan data.

---

## 🛠️ Project Stack & Technologies

*   **Host Platform:** Blender 3D Viewport Addon (built for Blender 3.0.0+ / Python 3.10+).
*   **Core APIs:** Blender Python API (`bpy`), low-level Edit Mode mesh manipulation (`bmesh`), and fast structural KD-Trees (`mathutils.kdtree`).
*   **Landmark Storage:** Standard Blender vertex groups, specifically one named `"TopoFit_Landmarks"`.
*   **Deformation Storage:** Native Blender Shape Keys. Edits are strictly prevented on the "Basis" key to ensure non-destructive workflow.
*   **Fitting Algorithm:** Sparse landmark coordinates are interpolated across the rest of the mesh using a geodesic-distance-weighted Inverse Distance Weighting (IDW) algorithm.
*   **Configuration:** Custom `bpy.props.BoolProperty` and `StringProperty` are registered on `bpy.types.Scene` for user settings.

---

## 🗺️ Single-Mesh Fitting Workflow State-Machine

The addon is designed to provide a seamless, **100% Edit Mode-centric** user experience. The UI panel dynamically guides the user through the following sequential phases based on the mesh's current state:

1.  **Step 1: Designate Landmarks**
    *   **Goal:** Define key anatomical features that will control the deformation.
    *   **Action:** User selects vertices in **Edit Mode** and clicks **"Add Selected to Landmarks"**. This adds them to the `"TopoFit_Landmarks"` vertex group.
2.  **Step 2: Set Target Shape Key**
    *   **Goal:** Prevent accidental modifications to the original mesh geometry (the "Basis" shape key).
    *   **Action:** If the current active shape key is "Basis" or no shape keys exist, the UI prompts the user to select or create a custom target shape key (e.g., `"TopoFit_Target"`). The plugin offers an "Auto-Create Key" option in its settings for a one-click setup.
3.  **Step 3: Align Landmarks & Symmetrize**
    *   **Goal:** Precisely position the designated landmarks to match the target scan data, leveraging symmetry.
    *   **Action:** User can use **"Toggle Landmark Mask"** to isolate landmarks for easier manipulation. Landmarks are repositioned by dragging, and changes can be mirrored across the X-axis using **"Apply Symmetry"**. This operation is designed to be fully compatible with the Mask modifier.
4.  **Step 4: Fit Remaining Mesh**
    *   **Goal:** Smoothly propagate the landmark deformations to all non-landmark vertices.
    *   **Action:** User clicks **"Fit Remaining Mesh (IDW)"** in **Edit Mode**. The addon calculates and applies a geodesic-distance-weighted interpolation, fitting the entire mesh to the landmark positions.

---

## ⚠️ Critical Development Rules & Guardrails for AI Agents

When assisting with this codebase, **always adhere to the following architectural patterns and principles to maintain stability and prevent regressions:**

### 1. Viewport & Shape Key Synchronicity (The Golden Rule)
*   **Problem:** In Edit Mode, direct updates to BMesh shape layers (`bm.verts[idx][shape_layer]`) do not automatically reflect in the live viewport's `bm.verts[idx].co` coordinates. Operations that modify shape keys can also cause `v.co` to revert.
*   **Rule:** When modifying shape key vertex positions, you **must explicitly update both** the shape layer *and* the active Edit Mode coordinate:
    ```python
    bm.verts[idx][shape_layer] = new_pos # Update the shape key data
    bm.verts[idx].co = new_pos           # Update the live viewport coordinate
    ```
*   **Always Flush and Redraw:** After any significant mesh data modification, ensure Blender updates its internal state and redraws the viewport:
    ```python
    bm.normal_update()
    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)
    obj.data.update()
    # Safely redraw only if context.area exists (not in headless/CLI mode)
    if context.area:
        context.area.tag_redraw()
    ```

### 2. Guarding Against Hidden Vertices (Mask Modifiers)
*   **Problem:** When the "Toggle Landmark Mask" is active, Blender's internal BMesh may exclude hidden vertices from direct modification loops or selections.
*   **Rule:** Operators that need to modify *all* vertices, including those temporarily hidden by the `TopoFit_Landmark_Mask` modifier (e.g., `Apply Symmetry`, `Fit Remaining Mesh`), **must temporarily disable the modifier's viewport visibility** (`show_in_editmode = False`) before performing calculations, and re-enable it afterward.
    ```python
    mask_mod = obj.modifiers.get("TopoFit_Landmark_Mask")
    mask_was_active = False
    if mask_mod:
        mask_was_active = True
        mask_mod.show_in_editmode = False
        mask_mod.show_on_cage = False # Also consider cage display
        obj.update_tag() # Force dependency graph update
        context.view_layer.update() # Force viewport redraw
    # ... perform mesh modifications ...
    if mask_was_active and mask_mod:
        mask_mod.show_in_editmode = True
        mask_mod.show_on_cage = True
        obj.update_tag()
        context.view_layer.update()