import shutil
import os
import datetime
import re

def make_addon_zip(addon_dir="topofit", output_dir="release"):
    """
    Creates a distributable .zip file for the Blender addon.
    The .zip will contain the addon_dir directly at its root.

    Args:
        addon_dir (str): The name of the addon's main folder (e.g., "topofit").
        output_dir (str): The directory where the .zip file will be saved.
    """
    if not os.path.exists(addon_dir):
        print(f"Error: Addon directory '{addon_dir}' not found.")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Get version from __init__.py for filename
    version_tuple = (0, 0, 0)
    init_file_path = os.path.join(addon_dir, "__init__.py")
    if os.path.exists(init_file_path):
        with open(init_file_path, 'r') as f:
            for line in f:
                if "bl_info" in line and "'version'" in line:
                    match = re.search(r"'version':\s*\((\d+),\s*(\d+),\s*(\d+)\)", line)
                    if match:
                        version_tuple = tuple(map(int, match.groups()))
                        break
    
    version_string = f"{version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]}"
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    
    base_name = f"{addon_dir}_v{version_string}_{timestamp}"
    archive_path = os.path.join(output_dir, base_name)

    print(f"INFO: Creating addon archive for '{addon_dir}'...")
    print(f"INFO: Version detected: {version_string}")
    print(f"INFO: Output: {archive_path}.zip")

    # shutil.make_archive automatically creates a .zip and places the contents
    # of the source directory (addon_dir) directly inside the zip.
    # The root_dir argument specifies the directory from which to start the archive.
    # The base_dir argument specifies the directory to start archiving from within root_dir.
    # To have 'topofit' folder directly inside the zip, we set root_dir to parent and base_dir to 'topofit'.
    current_working_dir = os.path.abspath(os.curdir)
    shutil.make_archive(archive_path, 'zip', root_dir=current_working_dir, base_dir=addon_dir)
    print("INFO: Packaging complete!")

if __name__ == "__main__":
    make_addon_zip()