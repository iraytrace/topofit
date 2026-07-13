"""
This module serves as the entry point for the TopoFit Blender Addon.

It defines the addon's metadata (bl_info), registers all necessary
operators, panels, and properties, and handles their unregistration
when the addon is disabled.
"""

import bpy
from . import operators
from . import panels
from . import properties

bl_info = {
    "name": "TopoFit",
    "author": "Lee",
    "version": (1, 64, 0), # Updated version for tracking changes
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > TopoFit",
    "description": "Landmark-guided geodesic topology fitting and deformation.",
    "category": "Mesh",
}

# List of all classes to register
# Order matters: properties should be registered before operators/panels that use them.
_classes = (
    operators.TOPOFIT_OT_show_help,
    operators.TOPOFIT_OT_create_target_key,
    operators.TOPOFIT_OT_select_mirrored,
    operators.TOPOFIT_OT_add_to_landmarks,
    operators.TOPOFIT_OT_remove_from_landmarks,
    operators.TOPOFIT_OT_select_landmarks,
    operators.TOPOFIT_OT_toggle_landmark_mask,
    operators.TOPOFIT_OT_refresh_mirror_map,
    operators.TOPOFIT_OT_revert_to_basis,
    operators.TOPOFIT_OT_apply_symmetry,
    operators.TOPOFIT_OT_deform_detail_vertices,
    panels.TOPOFIT_PT_panel,
)

def register():
    """
    Registers all classes and custom properties when the addon is enabled.
    """
    # Register scene properties manually as they are defined in properties.py FIRST
    properties.register_properties()
    # Then register other classes
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    """
    Unregisters all classes and custom properties when the addon is disabled.
    Registration is done in reverse order to avoid dependency issues.
    """
    # Unregister in reverse order
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    # Unregister scene properties LAST
    properties.unregister_properties()

if __name__ == "__main__":
    register()
