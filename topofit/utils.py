"""
This module provides utility functions and constants used across the TopoFit addon.

It includes functions for managing addon status, retrieving landmark indices,
generating and storing mirror maps, ensuring shape key existence, building
mesh adjacency, and handling geodesic distance caching.
"""

import bpy
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree
from collections import defaultdict
import heapq
import webbrowser

# ---------------------------------------------------------------------------
# CONSTANTS & STATUS
# ---------------------------------------------------------------------------
STATUS_OK = 0
ERROR_NO_ACTIVE_MESH = 1
ERROR_NO_SHAPEKEYS = 2
ERROR_BASIS_ACTIVE = 3
ERROR_NO_LANDMARKS_GROUP = 4

# Global cache for geodesic distances to avoid re-computation
# Stored as {obj_name: {'mesh_ptr': id(obj.data), 'landmark_indices': frozenset(indices), 'adjacency': adj, 'distances': {lm_idx: {v_idx: dist}}}}
_distance_cache: dict = {}

# ---------------------------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------------------------

def get_topofit_status(context):
    """
    Determines the current status of the TopoFit addon for the active object.

    Args:
        context (bpy.context): The current Blender context.

    Returns:
        tuple: A tuple containing:
            - int: A status code (e.g., STATUS_OK, ERROR_NO_ACTIVE_MESH).
            - bpy.types.Object or None: The active mesh object if found, otherwise None.
    """
    obj = context.active_object
    if not (obj and obj.type == 'MESH'):
        return (ERROR_NO_ACTIVE_MESH, None)
    if not obj.data.shape_keys:
        return (ERROR_NO_SHAPEKEYS, obj)
    # Check for active_shape_key_index rather than active_shape_key
    if obj.active_shape_key_index == 0 and len(obj.data.shape_keys.key_blocks) > 0:
        return (ERROR_BASIS_ACTIVE, obj)
    vg = obj.vertex_groups.get("TopoFit_Landmarks")
    # Check if the group exists AND if it actually contains any landmarks
    if not vg or not get_landmark_indices(obj):
        return (ERROR_NO_LANDMARKS_GROUP, obj)
    return (STATUS_OK, obj)

def get_landmark_indices(obj):
    """
    Retrieves the indices of vertices belonging to the "TopoFit_Landmarks" vertex group.
    Safe for both Edit Mode and Object Mode.

    Args:
        obj (bpy.types.Object): The mesh object to inspect.

    Returns:
        list: A list of vertex indices that are part of the landmark group.
    """
    if not (obj and obj.type == 'MESH'):
        return []
    vg = obj.vertex_groups.get("TopoFit_Landmarks")
    if not vg:
        return []
        
    indices = []
    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table() # Ensure vertex indices are up-to-date
        
        weight_layer = bm.verts.layers.deform.active
        if not weight_layer:
            # If no deform layer, no vertex groups can have weights in BMesh
            return []
            
        for v in bm.verts:
            # Check if the vertex has this group assigned and weight is > 0.1 (to avoid tiny weights)
            if vg.index in v[weight_layer] and v[weight_layer][vg.index] > 0.1:
                indices.append(v.index)
        # bmesh.free(bm) is not needed in Blender 2.80+
    else:
        # If in Object Mode, fall back to standard mesh vertices
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group == vg.index and g.weight > 0.1:
                    indices.append(v.index)
                    break
    return indices

def generate_mirror_map(vertices, tolerance=1e-5):
    """
    Generates a mapping of symmetrical vertex pairs across the X-axis.

    This function identifies vertices that are symmetrical across the local X-axis
    within a given tolerance. It uses a KDTree for efficient nearest-neighbor
    searching. Midline vertices (those on the X-axis) are also identified.

    Args:
        vertices (bpy.types.MeshVertices): The collection of vertices from a Blender mesh data block.
        tolerance (float, optional): The maximum distance between a vertex and its
                                     mirrored counterpart to be considered symmetrical.
                                     Defaults to 1e-5.

    Returns:
        tuple: A tuple containing:
            - dict: A dictionary mapping vertex indices to their symmetrical partner's index.
                    Only non-midline, paired vertices are included.
            - list: A list of vertex indices that lie on the X-axis (midline).
    """
    mirror_map = {}
    midline_verts = []
    
    # Create a KDTree for efficient spatial lookups
    kd = KDTree(len(vertices))
    for i, v in enumerate(vertices):
        kd.insert(v.co, i)
    kd.balance()
    
    paired = set() # Keep track of vertices already paired
    
    for i, v in enumerate(vertices):
        if abs(v.co.x) < tolerance:
            # Vertex is on the X-axis (midline)
            midline_verts.append(i)
            continue
        
        if i in paired:
            # Skip if this vertex has already been paired as a partner to another
            continue
        
        # Calculate the mirrored coordinate
        mirrored_co = v.co.copy()
        mirrored_co.x *= -1
        
        # Find the nearest neighbor to the mirrored coordinate
        _co, partner_idx, dist = kd.find(mirrored_co)
        
        # If a partner is found within tolerance and it's not the same vertex
        if dist < tolerance and i != partner_idx:
            mirror_map[i] = partner_idx
            mirror_map[partner_idx] = i
            paired.add(i)
            paired.add(partner_idx)
            
    return mirror_map, midline_verts

def store_mirror_data(mesh, mirror_map, midline_verts):
    """
    Stores the generated mirror map and midline vertices in the mesh's ID properties.

    Args:
        mesh (bpy.types.Mesh): The mesh data block to store data on.
        mirror_map (dict): The dictionary containing mirror pairs.
        midline_verts (list): The list of midline vertex indices.
    """
    # Convert integer keys to strings for storage in Blender's ID properties
    mesh["mirror_map"] = {str(k): v for k, v in mirror_map.items()}
    mesh["midline_verts"] = midline_verts

def load_mirror_map(mesh):
    """
    Loads the mirror map and midline vertices from the mesh's ID properties.

    Args:
        mesh (bpy.types.Mesh): The mesh data block to load data from.

    Returns:
        tuple: A tuple containing:
            - dict: The loaded mirror map (integer keys).
            - list: The loaded midline vertex indices.
    """
    raw_mirror_map = mesh.get("mirror_map", {})
    # Convert string keys back to integers when loading
    mirror_map = {int(k): int(v) for k, v in raw_mirror_map.items()}
    midline_verts = [int(i) for i in mesh.get("midline_verts", [])]
    return mirror_map, midline_verts

def ensure_target_shape_key(obj, key_name):
    """
    Ensures a target shape key exists on the object and sets it as active.
    If no shape keys exist, a "Basis" key is created first.
    Switches to Object Mode to safely create shape keys, then returns to the original mode.

    Args:
        obj (bpy.types.Object): The object to ensure the shape key on.
        key_name (str): The name of the target shape key to create/activate.
    """
    original_mode = obj.mode
    if original_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    if not obj.data.shape_keys:
        obj.shape_key_add(name="Basis")

    kb = obj.data.shape_keys.key_blocks
    if key_name not in kb:
        new_key = obj.shape_key_add(name=key_name, from_mix=False)
        new_key.value = 1.0 # Ensure new key is fully active

    # Set the target key as active
    obj.active_shape_key_index = kb.keys().index(key_name)

    if original_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode=original_mode)

def build_adjacency(mesh_data):
    """
    Builds an adjacency list for the mesh vertices based on its edges,
    including edge lengths.

    Args:
        mesh_data (bpy.types.Mesh): The mesh data block.

    Returns:
        defaultdict: An adjacency list where keys are vertex indices
                     and values are lists of (neighbor_index, edge_length) tuples.
    """
    adj = defaultdict(list)
    verts = mesh_data.vertices
    for edge in mesh_data.edges:
        a, b = edge.vertices
        length = (verts[a].co - verts[b].co).length
        length = max(length, 1e-8) # Avoid division by zero for zero-length edges
        adj[a].append((b, length))
        adj[b].append((a, length))
    return adj

def populate_distance_cache(obj_name, obj, landmark_indices):
    """
    Populates the global geodesic distance cache for a given object and its landmarks.
    This function computes distances using Dijkstra's algorithm from each landmark.

    Args:
        obj_name (str): The name of the object.
        obj (bpy.types.Object): The mesh object.
        landmark_indices (set): A set of landmark vertex indices.

    Returns:
        dict: The computed distances from each landmark to other non-landmark vertices.
    """
    lm_set = frozenset(int(i) for i in landmark_indices)
    adjacency = build_adjacency(obj.data)
    distances = {}

    for lm_idx in lm_set:
        dist = {lm_idx: 0.0}
        heap = [(0.0, lm_idx)] # Min-heap for Dijkstra's
        
        while heap:
            d, v = heapq.heappop(heap)
            if d > dist.get(v, float('inf')):
                continue
            for nb, edge_len in adjacency.get(v, []):
                nd = d + edge_len
                if nd < dist.get(nb, float('inf')):
                    dist[nb] = nd
                    heapq.heappush(heap, (nd, nb))
        
        # Store distances only to non-landmark vertices, excluding self (d > 0.0)
        distances[lm_idx] = {v: d for v, d in dist.items() if v not in lm_set and d > 0.0}
    
    # Store in global cache
    _distance_cache[obj_name] = {
        'mesh_ptr': id(obj.data), # Use ID for robust mesh data change detection
        'landmark_indices': lm_set,
        'adjacency': adjacency,
        'distances': distances
    }
    return distances

def get_cached_distances(obj_name, obj, landmark_indices):
    """
    Retrieves geodesic distances and adjacency from the global cache if available and valid.

    Args:
        obj_name (str): The name of the object.
        obj (bpy.types.Object): The mesh object.
        landmark_indices (set): The current set of landmark vertex indices.

    Returns:
        tuple: A tuple containing:
            - dict or None: Cached distances if found, else None.
            - dict or None: Cached adjacency if found, else None.
            - bool: True if cache hit and valid, False otherwise.
    """
    lm_set = frozenset(int(i) for i in landmark_indices)
    entry = _distance_cache.get(obj_name)
    
    # Check if entry exists, mesh data is the same object, and landmark set is identical
    if (entry is not None and
            entry['mesh_ptr'] == id(obj.data) and
            entry['landmark_indices'] == lm_set):
        return entry['distances'], entry['adjacency'], True
    return None, None, False

def invalidate_distance_cache(obj_name):
    """
    Invalidates (removes) the cached geodesic distances for a given object.

    Args:
        obj_name (str): The name of the object whose cache should be invalidated.
    """
    _distance_cache.pop(obj_name, None)
