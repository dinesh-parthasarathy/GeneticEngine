from typing import Iterator

from geneticengine.algorithms.api import ProgressTracker

from geneticengine.solutions import Individual


class Population:
    def __init__(self, it: Iterator[Individual], tracker: ProgressTracker, generation: int = -1):
        self.tracker = tracker
        self.individuals = []
        for ind in it:
            ind.metadata["generation"] = generation
            #self.tracker.evaluate_single(ind)
            self.individuals.append(ind)
        self.tracker.evaluate(self.individuals)
    def __iter__(self):
        return iter(self.individuals)
