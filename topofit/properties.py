"""
This module defines custom `bpy.types.PropertyGroup` classes and properties
used by the TopoFit addon. These properties are typically stored in the
Blender scene, allowing addon settings to persist with the blend file.
"""

import bpy

class TopoFit_SceneProperties(bpy.types.PropertyGroup):
    """
    Custom properties for the TopoFit addon stored in the scene.
    These properties control various aspects of the addon's behavior and UI state.
    """
    topofit_auto_create_key: bpy.props.BoolProperty(
        name="Auto-Create Shape Key",
        description="Automatically initialize basis and create/set active shape key when landmark group is created.",
        default=True
    )
    topofit_target_key_name: bpy.props.StringProperty(
        name="Target Key Name",
        description="Name of the custom shape key to create/use for deformation fitting.",
        default="TopoFit_Target"
    )
    topofit_falloff_power: bpy.props.FloatProperty( # Added property for falloff power
        name="Falloff Power",
        description="Exponent for inverse-distance weighting. Higher values localize landmark influence.",
        default=2.0, min=0.5, max=8.0
    )
    topofit_max_influence_distance: bpy.props.FloatProperty( # Added property for max influence distance
        name="Max Influence Distance",
        description="Maximum geodesic distance for a landmark to influence other vertices (0 = unlimited).",
        default=0.0, min=0.0
    )
    topofit_show_settings: bpy.props.BoolProperty(
        name="Show Settings",
        description="Show or hide addon settings panel.",
        default=False # Collapsed by default
    )
    topofit_show_status_guidance: bpy.props.BoolProperty(
        name="Show Status & Guidance",
        description="Show or hide current addon status and workflow guidance panel.",
        default=False # Collapsed by default
    )


def register_properties():
    """
    Registers the TopoFit_SceneProperties class and links it to bpy.types.Scene.
    """
    bpy.utils.register_class(TopoFit_SceneProperties)
    bpy.types.Scene.topofit_props = bpy.props.PointerProperty(type=TopoFit_SceneProperties)


def unregister_properties():
    """
    Unregisters the TopoFit_SceneProperties class and removes its link from bpy.types.Scene.
    """
    del bpy.types.Scene.topofit_props
    bpy.utils.unregister_class(TopoFit_SceneProperties)
