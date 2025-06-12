import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
import math
from sklearn.neighbors import BallTree
import numpy as np
from helpers.RAG import RAGPlatform
import networkx as nx
###########################################################################################################
# route optimisation function:
# input: list of place names from CSV.
# output: permutation of indexes based on input e.g. [0,2,3,5,1,4]
def solve_route(place_names, dist_mat, name_to_index):
    # fetch distance matrix
    distance_matrix = pd.DataFrame(list(dist_mat.find({}, {"_id": 0})))
    # remove first column which contains names of locations.
    distance_matrix = distance_matrix.drop(columns=distance_matrix.columns[0])
    # get index of place from csv file
    indices = [name_to_index[name] for name in place_names]
    # Fetch distance matrix subset
    subset_matrix = distance_matrix.iloc[indices, indices]
    # Run TSP pacakge
    permutation = solve_tsp(subset_matrix)
    return permutation

def solve_tsp(distance_matrix):
    # Handle inf values and NA values:
    distance_matrix = distance_matrix.replace([float('inf'), -float('inf')], 1e9)  # Replace inf with a large value
    distance_matrix = distance_matrix.fillna(0)  # Replace NaNs with 0 or an appropriate value
    # Create the routing index manager
    scaled_distance_matrix = (distance_matrix * 1000).round().astype(int)
    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), 1, 0)

    # Create the routing model
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        """Returns the distance between the two nodes."""
        # Convert from routing variable Index to distance matrix NodeIndex.
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return scaled_distance_matrix.iloc[from_node, to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    # Define cost of each arc
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Setting first solution heuristic
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.SAVINGS)
    def print_solution(manager, routing, solution):
        """Prints solution on console."""
        print(f"Objective: {solution.ObjectiveValue()/1000} m")
        index = routing.Start(0)
        plan_output = "Route for vehicle 0:\n"
        route_distance = 0
        while not routing.IsEnd(index):
            plan_output += f" {manager.IndexToNode(index)} ->"
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(previous_index, index, 0)
        plan_output += f" {manager.IndexToNode(index)}\n"
        plan_output += f"Route distance: {route_distance/1000}m\n"
        print(plan_output)
    # Solve the problem
    solution = routing.SolveWithParameters(search_parameters)
    print_solution(manager,routing,solution)

    # Get the solution and extract the optimal sequence
    if solution:
        index = routing.Start(0)
        optimal_sequence = []
        while not routing.IsEnd(index):
            optimal_sequence.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        optimal_sequence.append(manager.IndexToNode(index))  # Add the start point to complete the loop
        # sentosa use open routing, use set to remove duplicates.
        return optimal_sequence[:-1]
    else:
        return None
    
def get_distance_from_poi(poi, user_location):
    def haversine(coord1, coord2):
        # Coordinates in decimal degrees (e.g. (lng, lat))
        lon1, lat1 = coord1
        lon2, lat2 = coord2
        
        # Radius of Earth in meters
        R = 6371000  
        
        # Convert decimal degrees to radians
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        # Haversine formula
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        # Distance in meters
        distance = R * c
        
        return distance
    if poi and 'longitude' in poi and 'latitude' in poi:
        # Extract the coordinates from the MongoDB result
        poi_coord = (poi['longitude'], poi['latitude'])
        
        # Calculate the distance using the Haversine formula
        distance = haversine(poi_coord, user_location)
        print(f"== Distance from POI == {distance}")
        return distance
    else:
        return None
    
def haversine_np(lon1, lat1, lon2, lat2):
    # Convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    km = 6371 * c
    return km * 1000  # Convert to meters

    
def find_nearby_with_tree(ball_tree, poi_df, user_location, radius_m=100):
    user_coords_rad = np.radians([[user_location['latitude'], user_location['longitude']]])
    radius_radians = radius_m / 6371000  # Earth radius in meters

    indices = ball_tree.query_radius(user_coords_rad, r=radius_radians)[0]

    results = poi_df.iloc[indices].copy()
    results['distance_m'] = (
        6371000 * np.ravel(
            haversine_np(user_location['longitude'], user_location['latitude'],
                         results['longitude'], results['latitude'])
        )
    )

    return results.sort_values('distance_m')[['name', 'latitude', 'longitude', 'distance_m']].to_dict(orient='records')

def build_balltree_from_rag_platform(rag_platform: RAGPlatform):
    all_pois = []

    for unit in rag_platform.units.values():
        try:
            df = unit.get_location_data()
            if not df.empty:
                all_pois.append(df)
        except Exception as e:
            print(f"[{unit.id}] Failed to fetch location data: {e}")

    if not all_pois:
        raise ValueError("No POIs with valid coordinates found.")

    combined_df = pd.concat(all_pois, ignore_index=True)
    coords_rad = np.radians(combined_df[['latitude', 'longitude']].values)
    tree = BallTree(coords_rad, metric='haversine')

    return tree, combined_df

def update_ball_tree(poi_df):
    coordinates_rad = np.radians(poi_df[['latitude', 'longitude']].values)
    ball_tree = BallTree(coordinates_rad, metric='haversine')
    return ball_tree

def solve_route_with_balltree(place_names, poi_df, tree):
    dist_df = build_distance_matrix_from_balltree(place_names, poi_df, tree)
    permutation = solve_tsp(dist_df)
    return permutation

def build_distance_matrix_from_balltree(place_names, poi_df, tree):
    # Get indices and coordinates for selected POIs
    name_to_index = {name: idx for idx, name in enumerate(poi_df['name'])}
    indices = [name_to_index[name] for name in place_names]
    coords_subset = np.radians(poi_df.iloc[indices][['latitude', 'longitude']].to_numpy())
    
    # Use haversine distance (returns in radians, multiply by Earth's radius to get meters)
    earth_radius = 6371000  # in meters
    dist_matrix = np.zeros((len(indices), len(indices)))
    
    for i, coord in enumerate(coords_subset):
        # BallTree returns distance to all points (including itself)
        dists, _ = tree.query([coord], k=len(coords_subset))
        dist_matrix[i] = dists[0][:len(indices)] * earth_radius

    return pd.DataFrame(dist_matrix, index=place_names, columns=place_names)


def build_graph_from_balltree(poi_df, tree, coords_rad, k=5):
    earth_radius = 6371000  # in meters
    G = nx.Graph()

    names = poi_df['name'].tolist()
    for i, name in enumerate(names):
        G.add_node(name, pos=(poi_df.loc[i, 'longitude'], poi_df.loc[i, 'latitude']))

        # Query k nearest neighbors (excluding self)
        dist, ind = tree.query([coords_rad[i]], k=k+1)
        for j, d in zip(ind[0][1:], dist[0][1:]):  # skip self
            neighbor_name = names[j]
            distance_m = d * earth_radius
            G.add_edge(name, neighbor_name, weight=distance_m)

    return G