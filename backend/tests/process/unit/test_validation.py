import pytest

from src.process.domain.steps import STEPS
from src.process.domain.validation import WorkflowValidationError, validate
from tests.process.unit.routes import RouteBuilder, express


def problems(builder: RouteBuilder) -> list[str]:
    with pytest.raises(WorkflowValidationError) as error:
        validate(builder.build(), STEPS)
    return error.value.problems


def test_express_route_is_valid() -> None:
    validate(express(), STEPS)


def test_start_and_end() -> None:
    b = RouteBuilder().task("start_review").end("e").chain("start_review", "e")
    assert "exactly one start event expected, found 0" in problems(b)
    b = RouteBuilder().start().task("start_review").chain("start", "start_review")
    found = problems(b)
    assert "no end event" in found


def test_unknown_node_in_flow() -> None:
    b = RouteBuilder().start().end("e").flow("start", "nowhere")
    assert problems(b) == ["flow f1 refers to unknown node nowhere"]


def test_unreachable_and_dead_end_nodes() -> None:
    b = RouteBuilder().start().task("start_review").task("reject").end("e")
    b.chain("start", "start_review", "e").flow("reject", "reject")
    found = problems(b)
    assert "node reject is not reachable from start" in found
    assert "node reject never reaches an end" in found


def test_outgoing_flows() -> None:
    b = RouteBuilder().start().task("start_review").end("e").end("e2")
    b.chain("start", "start_review", "e").flow("start_review", "e2").flow("e", "e2")
    found = problems(b)
    assert "task start_review needs exactly one outgoing flow" in found
    assert "end e has outgoing flows" in found


def test_gateway_rules() -> None:
    b = RouteBuilder().start().gateway("gw").end("a").end("b")
    b.chain("start", "gw").flow("gw", "a", default=True).flow("gw", "b")
    found = problems(b)
    assert "flow f3 out of gateway gw has no condition" in found

    b = RouteBuilder().start().gateway("gw").end("a").end("b")
    b.chain("start", "gw").flow("gw", "a", when="complete == true").flow("gw", "b", when="complete")
    assert "gateway gw needs exactly one default flow" in problems(b)


def test_steps_must_exist_and_fit_the_node() -> None:
    b = RouteBuilder().start().task("t", step="launch_rockets").end("e").chain("start", "t", "e")
    assert problems(b) == ["t: unknown step 'launch_rockets'"]

    b = RouteBuilder().start().task("wait_signature").end("e").chain("start", "wait_signature", "e")
    assert problems(b) == ["wait_signature: step wait_signature is stoppable, it cannot be a task"]
    b = RouteBuilder().start().user("disburse").end("e").chain("start", "disburse", "e")
    assert problems(b) == ["disburse: step disburse is immediate, it cannot be a user_task"]


def test_loops_need_a_limit() -> None:
    b = RouteBuilder().start().task("request_info").user("wait_client_info").gateway("gw").end("e")
    b.chain("start", "request_info", "wait_client_info", "gw")
    b.flow("gw", "request_info", when="info_provided == false").flow("gw", "e", default=True)
    [problem] = problems(b)
    assert problem.startswith("loop ") and "has no node with max_iterations" in problem

    b.nodes["wait_client_info"] = b.nodes["wait_client_info"].__class__(
        "wait_client_info",
        b.nodes["wait_client_info"].type,
        "",
        "wait_client_info",
        b.nodes["wait_client_info"].config.__class__(max_iterations=2),
    )
    validate(b.build(), STEPS)
