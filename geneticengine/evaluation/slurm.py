import os
import json
import time
from pathlib import Path
from typing import Iterable
from geneticengine.evaluation.api import Evaluator
from geneticengine.problems import Problem,Fitness
from geneticengine.solutions.individual import Individual
import subprocess
class SLURMEvaluator(Evaluator):

    def __init__(self, output_dir: str, slurm_script: str, program_generator, output_parser=None):
        super().__init__()
        self.output_dir = Path(output_dir)
        self.slurm_script = slurm_script
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.program_generator = program_generator
        self.output_parser = output_parser
        self.num_jobs = 0
    def evaluate_async(self, problem: Problem, individuals: Iterable[Individual]):
        '''
        # Save each individual's representation to a file for SLURM processing
        individuals = list(individuals)
        for i, ind in enumerate(individuals):
            ind_str = self.program_generator(ind)
            file_name = f"individual_{i}"
            with open(f"{self.output_dir}/{file_name}", "w") as f:
                f.write(ind_str)

        self.num_jobs = len(individuals)

        # Submit an array job
        result = subprocess.run(
            ["sbatch", self.slurm_script],
            capture_output=True,
            text=True,
            check=True
        )
        jobid = int(result.stdout.strip().split()[-1])  # Extract job ID from the output

        print(f"Submitted SLURM array job with ID: {jobid}")
        # Wait for SLURM jobs to complete
        self._wait_for_jobs(jobid)
        print("All SLURM jobs completed.")
        '''
        individuals = list(individuals)  # Convert the iterator to a list
        self.num_jobs = len(individuals)
        # Aggregate results
        fitness_results = self._aggregate_results()
        for ind, fitness in zip(individuals, fitness_results):
            ind.set_fitness(problem, fitness)
            self.register_evaluation(ind, problem)
            yield ind

        print("All individuals evaluated.")
        print(f"Fitness results: {fitness_results}")
    def _wait_for_jobs(self, jobid: int):
        def array_still_running(jobid: int) -> bool:
            """
            Return True if any element of the array job is still PENDING or RUNNING.
            """
            result = subprocess.run(
                ["sacct", "-j", str(jobid), "-X", "--noheader", "--parsable2", "--format=State"],
                capture_output=True,
                text=True
            )
            states = {line.strip().split()[0] for line in result.stdout.splitlines() if line.strip()}
            return any(state in {"PENDING", "RUNNING"} for state in states)
        """Wait for SLURM jobs to complete."""
        while array_still_running(jobid):
            time.sleep(2000)

    def _aggregate_results(self):
        """Aggregate fitness results from all SLURM jobs."""
        fitness_results = []
        for i in range(self.num_jobs):
            result_file = f"{self.output_dir}/individual_out_{i}"
            fitness_results.append(Fitness([self.output_parser(result_file)]))
        return fitness_results