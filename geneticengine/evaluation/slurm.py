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

    def evaluate_async(self, problem: Problem, individuals: Iterable[Individual]):
        all_individuals = list(individuals)

        # Split: already evaluated vs. new individuals that need SLURM jobs
        cached = [ind for ind in all_individuals if ind.has_fitness(problem)]
        new_individuals = [ind for ind in all_individuals if not ind.has_fitness(problem)]

        # Yield already-evaluated individuals immediately
        for ind in cached:
            yield ind

        if not new_individuals:
            return

        # Save each new individual's representation to a file for SLURM processing
        for i, ind in enumerate(new_individuals):
            ind_str = self.program_generator(ind)
            file_name = f"individual_{i}"
            with open(f"{self.output_dir}/{file_name}", "w") as f:
                f.write(ind_str)

        num_jobs = len(new_individuals)

        # Remove results of previous generations, so that stale files can never be read as new results
        for old_result in self.output_dir.glob("individual_out_*"):
            old_result.unlink()

        # Submit an array job with dynamic array size
        result = subprocess.run(
            ["sbatch", f"--array=0-{num_jobs - 1}", self.slurm_script],
            capture_output=True,
            text=True,
            check=True
        )
        jobid = int(result.stdout.strip().split()[-1])  # Extract job ID from the output

        print(f"Submitted SLURM array job with ID: {jobid}")
        # Wait for SLURM jobs to complete
        self._wait_for_jobs(jobid)
        print("All SLURM jobs completed.")
        # Aggregate results
        fitness_results = self._aggregate_results(num_jobs)
        for ind, fitness in zip(new_individuals, fitness_results):
            ind.set_fitness(problem, fitness)
            self.register_evaluation(ind, problem)
            yield ind

        print(f"{num_jobs} new individual(s) evaluated via SLURM.")
        print(f"Fitness results: {fitness_results}")
    POLL_SECONDS = 5
    MAX_FAILED_POLLS = 120  # consecutive polls without an answer from Slurm before giving up (~10 min)

    def _queue_state(self, jobid: int) -> bool | None:
        """Whether any element of the array job is still in the queue (squeue needs no accounting database).
        Returns None if Slurm could not be asked."""
        result = subprocess.run(
            ["squeue", "-h", "-j", str(jobid), "-o", "%T"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
        if "Invalid job id" in result.stderr:
            return False  # the job has left the queue
        return None

    def _accounting_state(self, jobid: int) -> bool | None:
        """Same question answered by sacct. Returns None if sacct fails or knows nothing about the job yet."""
        result = subprocess.run(
            ["sacct", "-j", str(jobid), "-X", "--noheader", "--parsable2", "--format=State"],
            capture_output=True,
            text=True,
        )
        states = {line.strip().split()[0] for line in result.stdout.splitlines() if line.strip()}
        if result.returncode != 0 or not states:
            return None
        return any(state in {"PENDING", "RUNNING", "COMPLETING", "REQUEUED", "SUSPENDED"} for state in states)

    def _wait_for_jobs(self, jobid: int):
        """Wait for SLURM jobs to complete. A failure to reach Slurm is never taken as completion."""
        failed_polls = 0
        while True:
            running = self._queue_state(jobid)
            if running is None:
                running = self._accounting_state(jobid)
            if running is None:
                failed_polls += 1
                if failed_polls >= self.MAX_FAILED_POLLS:
                    raise RuntimeError(f"Could not get the state of SLURM job {jobid} from squeue or sacct.")
            else:
                failed_polls = 0
                if not running:
                    return
            time.sleep(self.POLL_SECONDS)

    def _aggregate_results(self, num_jobs: int):
        """Aggregate fitness results from all SLURM jobs. output_parser returns the list of objective values."""
        fitness_results = []
        for i in range(num_jobs):
            result_file = f"{self.output_dir}/individual_out_{i}"
            if not os.path.exists(result_file):
                print(f"WARNING: no output for individual {i} (task lost?); it is scored as a failed run.")
                open(result_file, "w").close()
            fitness_results.append(Fitness(self.output_parser(result_file)))
        return fitness_results
