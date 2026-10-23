"""Errors of loading a route: a broken BPMN file stops the application start."""


class ConditionError(ValueError):
    pass


class WorkflowValidationError(ValueError):
    def __init__(self, code: str, problems: list[str]) -> None:
        self.code = code
        self.problems = problems
        super().__init__(f"Workflow {code} is invalid: " + "; ".join(problems))
