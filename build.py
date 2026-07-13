import shutil
import os
import datetime
import ast
import sys

# --- Utility Functions ---

def get_addon_version_from_init(init_file_path):
    """
    Parses __init__.py using the AST module to robustly find bl_info['version'].
    Returns a version tuple (major, minor, patch).
    """
    with open(init_file_path, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=init_file_path)

    bl_info_dict = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'bl_info':
                    if isinstance(node.value, ast.Dict):
                        bl_info_dict = node.value
                        break
            if bl_info_dict:
                break
    
    if bl_info_dict:
        for key, value in zip(bl_info_dict.keys, bl_info_dict.values):
            if isinstance(key, ast.Constant) and key.value == 'version':
                if isinstance(value, ast.Tuple):
                    version_tuple = tuple(v.value for v in value.elts if isinstance(v, ast.Constant))
                    # Ensure version is at least (X, Y, Z) by padding with 0s if shorter
                    while len(version_tuple) < 3:
                        version_tuple += (0,)
                    return version_tuple
    
    raise ValueError(f"Could not find 'bl_info['version']' tuple in {init_file_path}. Expected format: ('version': (X, Y, Z))")

# --- Main Build Function ---

def make_addon_zip(addon_dir="topofit", output_dir="release", 
                   manifest_template_filename="blender_manifest.toml.template",
                   generated_manifest_filename="blender_manifest.toml"):
    """
    Creates a distributable .zip file for the Blender addon.
    Generates blender_manifest.toml from a template using the version from __init__.py.
    The .zip will contain the addon_dir directly at its root.
    """
    if not os.path.exists(addon_dir):
        print(f"Error: Addon directory '{addon_dir}' not found.")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 1. Get version from __init__.py
    init_file_path = os.path.join(addon_dir, "__init__.py")
    try:
        version_tuple = get_addon_version_from_init(init_file_path)
        version_string = f"{version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]}"
    except ValueError as e:
        print(f"Error: {e}. Defaulting version to 0.0.0 for zip name and manifest.")
        version_string = "0.0.0"

    # 2. Generate blender_manifest.toml from template
    manifest_template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), manifest_template_filename)
    generated_manifest_path = os.path.join(addon_dir, generated_manifest_filename)
    
    try:
        with open(manifest_template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Replace the placeholder with the actual version string
        final_manifest_content = template_content.replace("{version_placeholder}", version_string)
        
        with open(generated_manifest_path, 'w', encoding='utf-8') as f:
            f.write(final_manifest_content)
        print(f"INFO: Generated '{generated_manifest_filename}' in '{addon_dir}' with version '{version_string}'.")
    except FileNotFoundError:
        print(f"Error: Manifest template file '{manifest_template_path}' not found. Cannot generate manifest.")
        return
    except Exception as e:
        print(f"Error generating manifest from template: {e}")
        return

    # 3. Create zip file
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"{addon_dir}_v{version_string}_{timestamp}"
    archive_path = os.path.join(output_dir, base_name)

    print(f"\nINFO: Creating addon archive for '{addon_dir}'...")
    print(f"INFO: Using version: {version_string}")
    print(f"INFO: Output: {archive_path}.zip")

    current_working_dir = os.path.abspath(os.curdir)
    shutil.make_archive(archive_path, 'zip', root_dir=current_working_dir, base_dir=addon_dir)
    print("INFO: Packaging complete!")

    # 4. Clean up the generated blender_manifest.toml
    try:
        os.remove(generated_manifest_path)
        print(f"INFO: Cleaned up temporary '{generated_manifest_filename}'.")
    except Exception as e:
        print(f"Warning: Could not remove temporary manifest file '{generated_manifest_path}': {e}")

if __name__ == "__main__":
    make_addon_zip()
