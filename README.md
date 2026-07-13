# TopoFit Blender Addon

## Project Overview

**TopoFit** is an elegant, non-destructive, single-mesh landmark-guided shape deformation addon for Blender. It streamlines the process of fitting a clean base topology (like a standard human character) to raw, potentially messy, high-resolution 3D scan data.

This addon operates entirely within Blender's Edit Mode, offering a seamless and intuitive user experience by leveraging vertex groups, shape keys, and custom viewport masking.

## User Documentation

For detailed instructions on how to use the TopoFit addon within Blender, please refer to the [User Help Documentation](topofit/doc/help.html).

## Developer Setup & Getting Started

To set up this project for development in VSCode with the Blender Development extension:

### 1. Project Structure

Ensure your project structure matches the following. Your addon code lives in the `topofit/` subfolder:

```
your_repo_root/
├── topofit/                  <-- Main addon folder
│   ├── __init__.py           
│   ├── operators.py          
│   ├── panels.py             
│   ├── properties.py         
│   ├── utils.py              
│   └── doc/                  <-- HTML documentation for the addon
│       └── help.html
├── test_topofit.py           <-- Automated test suite for the addon
├── blender_manifest.toml     <-- Blender extension manifest
├── CONTINUE.md               <-- AI agent development guidelines (this file)
└── README.md                 <-- This file
```

### 2. VSCode Blender Development Extension

Install the official "Blender Development" extension for VSCode by Jacques Lucke.

### 3. Configure VSCode Settings

Update your `.vscode/settings.json` file (create it if it doesn't exist in your repo's `.vscode` folder) to point to your addon's main directory and your Blender executable:

```json .vscode/settings.json
{
    "blender.addon.path": "${workspaceFolder}/topofit",
	"blender.addon.loadDirectory": "topofit",
	"blender.addon.sourceDirectory": "topofit",
    "blender.executables": {
        "blender5.1": "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" // Adjust to your Blender install path
    }
    // Add other Blender versions as needed, or set "default"
}
```

### 4. Install/Enable the Addon in Blender

For development, Blender needs to find your addon.
1.  In Blender, go to `Edit > Preferences > File Paths`.
2.  Under `Script Directories`, add the path to your `your_repo_root/` folder (the parent of your `topofit` folder).
3.  Go to `Edit > Preferences > Add-ons`.
4.  Search for "TopoFit". If it doesn't appear, refresh (F8 in Blender's viewport or the "Refresh" button in preferences).
5.  Enable the "TopoFit" addon by checking its box.

## Running Tests

The project includes a robust automated test suite.

### 1. Run Tests with Blender GUI (Visual Inspection)

This command launches Blender, runs the tests, and keeps the Blender GUI open so you can visually inspect the results.

```bash
"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --python test_topofit.py
```
*(Adjust the Blender executable path as per your `settings.json`)*

### 2. Run Tests Headlessly (CI/Quick Checks)

This command runs Blender in the background, executes the tests, and immediately exits. The results are printed to your terminal. Ideal for quick verification and Continuous Integration environments.

```bash
"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python test_topofit.py
~~~
*(Adjust the Blender executable path as per your `settings.json`)*

## Packaging for Distribution

To create a distributable `.zip` file for sharing your addon:

1.  Navigate to your `topofit/` folder in your file explorer.
2.  Select the entire `topofit` folder.
3.  Compress it into a `.zip` file.
    *   **Important:** The `.zip` file should contain the `topofit` folder directly inside it (e.g., `topofit.zip` extracts to `topofit/__init__.py`, `topofit/operators.py`, etc., NOT `some_folder/topofit/__init__.py`).

## AI Agent Development Guidelines

This repository includes a dedicated file, [`CONTINUE.md`](CONTINUE.md), which provides specific instructions, architectural patterns, and guardrails for AI agents assisting with the development of this project. Developers (human or AI) are encouraged to consult this document for deep context.