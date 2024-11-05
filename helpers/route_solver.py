import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

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
        return list(set(optimal_sequence))
    else:
        return None