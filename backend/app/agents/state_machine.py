from enum import StrEnum


class AgentState(StrEnum):
    IDLE = "idle"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStateMachine:
    def __init__(self) -> None:
        self.state = AgentState.IDLE

    def transition_to(self, next_state: AgentState) -> AgentState:
        allowed_transitions: dict[AgentState, set[AgentState]] = {
            AgentState.IDLE: {AgentState.PLANNING, AgentState.RUNNING},
            AgentState.PLANNING: {AgentState.RUNNING, AgentState.WAITING, AgentState.FAILED},
            AgentState.RUNNING: {AgentState.WAITING, AgentState.COMPLETED, AgentState.FAILED},
            AgentState.WAITING: {AgentState.RUNNING, AgentState.FAILED},
            AgentState.COMPLETED: {AgentState.IDLE},
            AgentState.FAILED: {AgentState.IDLE},
        }
        if next_state not in allowed_transitions[self.state]:
            raise ValueError(f"Invalid agent transition: {self.state} -> {next_state}")

        self.state = next_state
        return self.state
