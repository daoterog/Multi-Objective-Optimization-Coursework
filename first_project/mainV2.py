import argparse
import heapq
import math
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

DATA_PATH = Path.cwd() / "data" / "SPP.csv"
VALID_COST_METHODS = {"weighted", "lexic", "mixture"}


@dataclass
class Costs:
    distance: int
    emission: int
    risk: int

    def __add__(self, other: "Costs") -> "Costs":
        return Costs(
            self.distance + other.distance,
            self.emission + other.emission,
            self.risk + other.risk,
        )

    def to_list(self) -> List[int]:
        return [self.distance, self.emission, self.risk]

    def __repr__(self) -> str:
        return f"distance={self.distance}, emission={self.emission}, risk={self.risk},"


@dataclass
class Node:
    cur_node: int
    costs: Costs


@dataclass
class PathToNode:
    cur_node: int
    costs: Costs
    total_cost: float
    path: list

    def __lt__(self, other: "PathToNode") -> bool:
        return self.total_cost < other.total_cost

    def __repr__(self) -> str:
        return f"Path to node {self.cur_node} with costs {self.costs} and total cost {self.total_cost}."


def arguments_santiy_check(kwargs: dict) -> None:
    """Check arguments validity."""

    if kwargs["cost_method"] not in VALID_COST_METHODS:
        raise ValueError(
            "Invalid cost method. Valid methods are: weighted, lexic, mixture."
        )

    if len(kwargs["weights"]) != 3:
        raise ValueError("Weights must have 3 values.")

    for weight in kwargs["weights"]:
        if weight < 0:
            raise ValueError("Weights must be positive.")

    if len(kwargs["order"]) != 3:
        raise ValueError("Order must have 3 values.")

    for num in [1, 2, 3]:
        if num not in kwargs["order"]:
            raise ValueError("Order must have 3 values from 1 to 3.")

    if kwargs["mixture_weight"] < 0.5 or kwargs["mixture_weight"] > 1:
        raise ValueError("Mixture weight must be between 0 and 1.")

    # Normalize weights
    total_sum = sum(kwargs["weights"])
    kwargs["weights"] = [weight / total_sum for weight in kwargs["weights"]]


def parse_arguments() -> dict:
    """Parse and return arguments from command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cost-method",
        type=str,
        default="mixture",
        help="Method to evaluate path costs.",
    )
    parser.add_argument(
        "--weights",
        type=float,
        nargs="+",
        default=[1, 1, 1],
        help="Weights to evaluate path costs.",
    )
    parser.add_argument(
        "--order",
        type=int,
        nargs="+",
        default=[1, 2, 3],
        help="Order to evaluate path costs.",
    )
    parser.add_argument(
        "--mixture-weight",
        type=float,
        default=0.7,
        help="Weight to give to objectives in squential algorithm.",
    )
    kwargs = vars(parser.parse_args())
    arguments_santiy_check(kwargs)
    return kwargs


def parse_line(
    line: str, max_costs: Costs, min_costs: Costs
) -> Tuple[Node, Node, Costs, Costs]:
    """Parse line from csv file and return two nodes."""

    # Retrieve data from line
    node_from, node_to, distance, emission, risk = line.split(",")

    # Convert data to correct type
    node_from, node_to = int(node_from), int(node_to)
    distance, emission, risk = float(distance), float(emission), float(risk)

    # Create Costs and Node objects
    costs = Costs(distance, emission, risk)
    node_from = Node(node_from, costs)
    node_to = Node(node_to, costs)

    # Update max and min costs
    max_costs = Costs(
        max(max_costs.distance, distance),
        max(max_costs.emission, emission),
        max(max_costs.risk, risk),
    )

    min_costs = Costs(
        min(min_costs.distance, distance),
        min(min_costs.emission, emission),
        min(min_costs.risk, risk),
    )

    return node_from, node_to, max_costs, min_costs


def read_data(path: Path) -> Tuple[int, Dict[int, Node], Costs, Costs]:
    """Read data from csv file and return number of node, and path dictionary."""

    with open(path, "r") as f:
        lines = f.read().split("\n")

        # Retrieve number of nodes
        n_nodes = int(lines[0].split(",")[0][-3:])

        # Store Max and Min values for each cost
        max_costs = Costs(-math.inf, -math.inf, -math.inf)
        min_costs = Costs(math.inf, math.inf, math.inf)

        # Create dictionary every possible paths
        paths = {}
        for line in lines[1:]:
            node_from, node_to, max_costs, min_costs = parse_line(
                line, max_costs, min_costs
            )

            if node_from.cur_node in paths:
                paths[node_from.cur_node].append(node_to)
            else:
                paths[node_from.cur_node] = [node_to]

            if node_to.cur_node in paths:
                for i, node in enumerate(paths[node_to.cur_node]):
                    # Iterate over the list to check if node_from is already in the list
                    if node.cur_node == node_from.cur_node:
                        # If node_from is already in the list then the edge is repeated
                        # Pop repeated path out of the list
                        paths[node_to.cur_node].pop(i)
                        break

                paths[node_to.cur_node].append(node_from)
            else:
                paths[node_to.cur_node] = [node_from]

    return n_nodes, paths, max_costs, min_costs


def normalize_costs(costs: Costs, max_costs: Costs, min_costs: Costs) -> Costs:
    """Normalize costs between 0 and 1."""

    # Normalize distance
    if max_costs.distance == min_costs.distance:
        distance = 0
    else:
        distance = (costs.distance - min_costs.distance) / (
            max_costs.distance - min_costs.distance
        )

    # Normalize emission
    if max_costs.emission == min_costs.emission:
        emission = 0
    else:
        emission = (costs.emission - min_costs.emission) / (
            max_costs.emission - min_costs.emission
        )

    # Normalize risk
    if max_costs.risk == min_costs.risk:
        risk = 0
    else:
        risk = (costs.risk - min_costs.risk) / (max_costs.risk - min_costs.risk)

    return Costs(distance, emission, risk)


def create_new_path(
    cur_path: PathToNode,
    to_node: Node,
    cost_method: str,
    max_costs: Costs,
    min_costs: Costs,
    weights: List[float] = [],
    constraints: List[float] = [],
) -> Tuple[PathToNode, Optional[bool]]:
    """Create new path to node."""

    # Recalculating costs with new node
    new_costs = cur_path.costs + normalize_costs(to_node.costs, max_costs, min_costs)

    # Computing weighted average
    new_total_cost = (
        new_costs.distance * weights[0]
        + new_costs.emission * weights[1]
        + new_costs.risk * weights[2]
    )

    is_feasible = True

    if cost_method != "weighted":
        # Check if new path maintains optimal cost for previous objectives
        violation = []
        for new_cost, constraint in zip(new_costs.to_list(), constraints):
            violation.append(new_cost <= constraint)
        is_feasible = all(violation)

    # Create new path with information
    new_path = PathToNode(
        to_node.cur_node,
        new_costs,
        new_total_cost,
        cur_path.path + [to_node.cur_node],
    )

    return new_path, is_feasible


def dijkstra(end_node: int, paths: Dict[int, Node], cost_kwargs: dict) -> PathToNode:
    """Dijkstra algorithm to find shortest path."""

    # Remove order from cost_kwargs to avoid errors
    if "order" in cost_kwargs:
        del cost_kwargs["order"]

    if "mixture_weight" in cost_kwargs:
        del cost_kwargs["mixture_weight"]

    # Initialize variables
    visited = set()
    cur_path = PathToNode(1, Costs(0, 0, 0), 0, [1])
    priority_queue = [cur_path]

    #  Use priority queue to find shortest path
    heapq.heapify(priority_queue)

    while priority_queue:
        # Get shortest path
        cur_path = heapq.heappop(priority_queue)
        cur_node = cur_path.cur_node

        if cur_node not in visited:
            #  Explore if node has not been visited
            visited.add(cur_node)
            for to_node in paths[cur_node]:
                # Explore all possible paths
                if to_node.cur_node not in visited:
                    # Create new path if node has not been visited
                    new_path, is_feasible = create_new_path(
                        cur_path, to_node, **cost_kwargs
                    )
                    if not is_feasible:
                        # Continue exploring other paths if new path is not feasible
                        continue
                    if new_path.cur_node == end_node:
                        # Return path if it reaches the end node
                        return new_path
                    # Add new path to priority queue only if it is feasible and has not
                    # reached the end node yet
                    heapq.heappush(priority_queue, new_path)

    # Return error message if no feasible path is found
    return "No feasible path found"


def sequential_optimization(
    order: List[List[float]], end_node: int, paths: Dict[int, Node], cost_kwargs: dict
) -> PathToNode:
    """Sequential optimization algorithm."""

    # Auxiliary variables to keep track of the last optimal solution
    last_objective_cost = math.inf
    cost_kwargs["constraints"] = [math.inf] * 3
    last_shortest_path = None

    # Optimize objectives in the specified order
    for i, weights in enumerate(order):
        # Update weights to optimize current objective
        cost_kwargs["weights"] = weights

        # Update constraints to preserve previous optimal solution
        index = weights.index(max(weights))
        cost_kwargs["constraints"][index] = last_objective_cost

        # Find shortest path
        shortest_path = dijkstra(end_node, paths, cost_kwargs)

        if isinstance(shortest_path, str):
            # If no feasible solution is found, stop the algorithm
            print(
                "There is no feasible solution that preserves previous optimal solution."
            )
            print(
                f"The previous optimal solution will be returned. It optimized the first {i} objectives."
            )
            print()
            return last_shortest_path

        # Update last optimal solution
        last_objective_cost = shortest_path.costs.to_list()[index]
        last_shortest_path = shortest_path

    return shortest_path


def lexicographic_method(
    end_node: int, paths: Dict[int, Node], kwargs: dict
) -> PathToNode:
    """Lexicographic method to find shortest path."""

    # Order in which objectives will be prioritized
    order = []
    for num in kwargs["order"]:
        # Set weights to 1 for the objective being optimized and 0 for the rest
        weights = [0, 0, 0]
        weights[num - 1] = 1
        order.append(weights)

    return sequential_optimization(order, end_node, paths, kwargs)


def mixture_method(end_node: int, paths: Dict[int, Node], kwargs: dict) -> PathToNode:
    """Mixture method to find shortest path."""

    # Order in which objectives will be prioritized
    order = []
    for num in kwargs["order"]:
        # Set the optimized objective to the specified mixture weight and the rest to
        # the remaining weights equally divided
        weights = [(1 - kwargs["mixture_weight"]) / 2] * 3
        weights[num - 1] = kwargs["mixture_weight"]
        order.append(weights)

    return sequential_optimization(order, end_node, paths, kwargs)


def normalize_weigth(weight):
    """Normalize weights."""
    return [round(w / sum(weight), 3) for w in weight]


def experimentation(n_nodes, paths, kwargs):
    """Run experiments to compare the performance of the algorithms."""
    table_results = []
    if kwargs["cost_method"] == "mixture":
        perm = list(permutations(kwargs["order"]))
        for w in perm:
            for i in range(5, 10):
                res = {}
                kwargs["order"] = w
                kwargs["mixture_weight"] = i / 10

                res["order"] = tuple(kwargs["order"])
                res["mixture_weight"] = kwargs["mixture_weight"]

                shortest_path = mixture_method(n_nodes, paths, kwargs)
                res["costs"] = tuple(np.round(shortest_path.costs.to_list(), 4))
                table_results.append(res)
    elif kwargs["cost_method"] == "lexic":
        table_results = []
        perm = list(permutations(kwargs["order"]))

        for w in perm:
            res = {}
            kwargs["order"] = w
            res["order"] = tuple(kwargs["order"])
            shortest_path = lexicographic_method(n_nodes, paths, kwargs)
            res["costs"] = tuple(np.round(shortest_path.costs.to_list(), 4))
            table_results.append(res)

    elif kwargs["cost_method"] == "weighted":
        table_results = []
        for i in list(permutations(range(0, 4), 3)):
            res = {}
            kwargs["weights"] = normalize_weigth(i)
            res["weights"] = tuple(kwargs["weights"])
            shortest_path = dijkstra(n_nodes, paths, kwargs)
            res["costs"] = tuple(np.round(shortest_path.costs.to_list(), 4))
            table_results.append(res)

    return table_results


def run_experiments(method):
    """Run experiments to compare the performance of the algorithms."""
    kwargs = {
        "cost_method": method,
        "weights": [0.333, 0.333, 0.333],
        "order": [1, 2, 3],
        "mixture_weight": 0.7,
    }

    n_nodes, paths, max_costs, min_costs = read_data(DATA_PATH)

    # Add max and min costs to kwargs
    kwargs["max_costs"] = max_costs
    kwargs["min_costs"] = min_costs

    results = experimentation(n_nodes, paths, kwargs)
    # dict to dataframe
    df = pd.DataFrame(results).to_latex(index=False)
    print(df)


if __name__ == "__main__":
    kwargs = parse_arguments()
    n_nodes, paths, max_costs, min_costs = read_data(DATA_PATH)

    # Add max and min costs to kwargs
    kwargs["max_costs"] = max_costs
    kwargs["min_costs"] = min_costs

    if kwargs["cost_method"] == "weighted":
        shortest_path = dijkstra(n_nodes, paths, kwargs)
    elif kwargs["cost_method"] == "lexic":
        shortest_path = lexicographic_method(n_nodes, paths, kwargs)
    elif kwargs["cost_method"] == "mixture":
        shortest_path = mixture_method(n_nodes, paths, kwargs)

    run_experiments("weighted")
