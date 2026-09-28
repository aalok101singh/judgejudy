"""The assignment engine: what is fair, what is possible, and what is not.

A package rather than an app, for the same reason ``reviewer.isolation`` and
``reviewer.importer`` are packages rather than apps: it defines no model, so
putting it in ``INSTALLED_APPS`` would add a ``models`` module that does not
exist and a migration that creates nothing.

Three modules, and the split is by *what has to be true* rather than by size:

* :mod:`reviewer.assignment.flow` -- a min-cost max-flow solver in pure Python.
  No knowledge of judging at all; it would work on a warehouse.
* :mod:`reviewer.assignment.graph` -- who may review what. The five eligibility
  rules, read from the database, with the edge count exposed so it can be pinned.
* :mod:`reviewer.assignment.planner` -- the service. Capacity search, the
  min-cost tidying pass, and the min-cut diagnosis.

The layering is load-bearing for the claim in ``bible/06`` §2.3 that the
diagnosis and the assignment *cannot* disagree, because both are read off one
network rather than computed by two code paths.
"""

from reviewer.assignment.graph import AssignmentGraph, build_graph
from reviewer.assignment.planner import AssignmentPlan, plan_assignment

__all__ = ["AssignmentGraph", "AssignmentPlan", "build_graph", "plan_assignment"]
