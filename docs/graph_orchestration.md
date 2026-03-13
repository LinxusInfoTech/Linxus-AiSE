# AiSEGraph Orchestration

## Overview

The AiSEGraph is a LangGraph-based state machine that orchestrates the complete AI Support Engineer workflow. It coordinates multiple specialized agents (Ticket Agent, Knowledge Agent, Engineer Agent) through a defined workflow with conditional routing based on operational mode.

## Architecture

```
┌─────────────┐
│   Classify  │  ← Classify ticket (if ticket_id present)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Retrieve   │  ← Retrieve relevant documentation
│  Knowledge  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Diagnose   │  ← Generate diagnosis
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Plan Tools  │  ← Plan tool execution (future)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│Execute Tools│  ← Execute diagnostic commands (future)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Generate   │  ← Generate final response
│  Response   │
└──────┬──────┘
       │
       ▼
    ┌──────┐
    │ Mode?│
    └──┬───┘
       │
       ├─ Approval ──→ Set Approval Gate ──→ END (pause)
       │
       ├─ Autonomous ──→ Post Reply ──→ END
       │
       └─ Interactive ──→ END (no reply)
```

## Workflow Steps

### 1. Classify Ticket

**When**: If `ticket_id` is present in state

**Actions**:
- Fetch ticket from provider
- Classify using Ticket Agent
- Extract category, severity, affected service
- Add suggested tags

**Output**: `ticket_analysis` in state

### 2. Retrieve Knowledge

**When**: If Knowledge Agent is available

**Actions**:
- Build query from ticket/messages
- Search vector store for relevant docs
- Return top 5 chunks

**Output**: `knowledge_context` in state

### 3. Diagnose

**When**: Always

**Actions**:
- Call Engineer Agent with context
- Generate diagnosis and troubleshooting plan
- Include knowledge context if available

**Output**: `diagnosis` in state

### 4. Plan Tools

**When**: Always (currently placeholder)

**Actions**:
- Analyze diagnosis for tool execution needs
- Plan which commands to run
- (Future implementation)

**Output**: Planned commands

### 5. Execute Tools

**When**: If tools are planned (currently skipped)

**Actions**:
- Execute planned commands
- Parse output
- (Future implementation)

**Output**: `tool_results` in state

### 6. Generate Response

**When**: Always

**Actions**:
- Finalize response based on diagnosis
- Currently uses existing diagnosis

**Output**: Final response ready

### 7. Approval Gate / Post Reply

**When**: Depends on mode

**Actions**:
- **Approval Mode**: Set `pending_approval` and pause
- **Autonomous Mode**: Post reply automatically
- **Interactive Mode**: Skip (no ticket)

**Output**: Reply posted or pending approval

## Operational Modes

### Interactive Mode

Used for direct CLI questions without ticket processing.

```python
state = create_initial_state(
    messages=[{"role": "user", "content": "Why is my EC2 unreachable?"}],
    mode="interactive"
)

final_state = await graph.run(state)
# Returns diagnosis, no ticket operations
```

**Characteristics**:
- No ticket classification
- No reply posting
- Direct diagnosis generation
- Immediate response

### Approval Mode

Requires human approval before posting replies to tickets.

```python
state = create_initial_state(
    messages=[{"role": "user", "content": "EC2 issue"}],
    mode="approval",
    ticket_id="ticket-123"
)

final_state = await graph.run(state)

if final_state["pending_approval"]:
    # Display proposed reply to user
    print(final_state["pending_approval"]["message"])
    
    # Wait for approval...
    # Then post reply manually
```

**Characteristics**:
- Full workflow execution
- Pauses before posting reply
- Sets `pending_approval` in state
- Requires manual confirmation

### Autonomous Mode

Fully automated ticket processing and reply posting.

```python
state = create_initial_state(
    messages=[{"role": "user", "content": "EC2 issue"}],
    mode="autonomous",
    ticket_id="ticket-123"
)

final_state = await graph.run(state)
# Reply automatically posted
```

**Characteristics**:
- Full workflow execution
- Automatic reply posting
- No human intervention
- Fastest response time

## State Management

### State Immutability

All agent functions maintain state immutability:

```python
# ✓ Correct: Returns new state
async def diagnose(self, state: AiSEState) -> AiSEState:
    return update_state(state, diagnosis="...")

# ✗ Wrong: Mutates input state
async def diagnose(self, state: AiSEState) -> AiSEState:
    state["diagnosis"] = "..."  # Don't do this!
    return state
```

### State Transitions

The graph tracks all state transitions:

```python
final_state["actions_taken"]
# ['Classified ticket', 'Retrieved documentation', 'Generated diagnosis', 'Posted reply']

final_state["updated_at"]
# '2024-03-14T10:30:45.123456'
```

## Usage Examples

### Basic Usage

```python
from aise.agents.graph import AiSEGraph
from aise.agents.state import create_initial_state

# Create graph
graph = AiSEGraph(
    ticket_agent=ticket_agent,
    knowledge_agent=knowledge_agent,
    engineer_agent=engineer_agent,
    ticket_provider=ticket_provider
)

# Create initial state
state = create_initial_state(
    messages=[{"role": "user", "content": "Question"}],
    mode="interactive"
)

# Execute
final_state = await graph.run(state)
```

### With Configuration

```python
from aise.agents.graph import AiSEGraph
from aise.core.config import get_config
from aise.ai_engine.router import LLMRouter

config = get_config()
llm_router = LLMRouter(config)

# Create from config
graph = AiSEGraph.from_config(
    config,
    llm_router,
    vector_store=vector_store,
    embedder=embedder,
    ticket_provider=ticket_provider
)
```

### Error Handling

```python
from aise.core.exceptions import ProviderError

try:
    final_state = await graph.run(state)
except ProviderError as e:
    logger.error(f"Graph execution failed: {e}")
    # Handle error
```

## Extending the Graph

### Adding New Nodes

```python
# 1. Add node to graph
workflow.add_node("my_node", self._my_node_impl)

# 2. Implement node function
async def _my_node_impl(self, state: AiSEState) -> AiSEState:
    # Process state
    return update_state(state, my_field="value")

# 3. Add edges
workflow.add_edge("previous_node", "my_node")
workflow.add_edge("my_node", "next_node")
```

### Adding Conditional Routing

```python
# 1. Add conditional edge
workflow.add_conditional_edges(
    "my_node",
    self._should_do_something,
    {
        "yes": "action_node",
        "no": "skip_node"
    }
)

# 2. Implement routing function
def _should_do_something(self, state: AiSEState) -> Literal["yes", "no"]:
    if state.get("some_condition"):
        return "yes"
    return "no"
```

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_graph_execution():
    # Create mocked dependencies
    mock_ticket_agent = MagicMock()
    mock_engineer_agent = MagicMock()
    
    # Create graph
    graph = AiSEGraph(
        ticket_agent=mock_ticket_agent,
        knowledge_agent=None,
        engineer_agent=mock_engineer_agent
    )
    
    # Execute
    state = create_initial_state(messages=[...])
    final_state = await graph.run(state)
    
    # Verify
    assert final_state["diagnosis"] is not None
```

### Integration Tests

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_workflow():
    # Use real dependencies
    graph = AiSEGraph.from_config(config, llm_router, ...)
    
    # Execute full workflow
    state = create_initial_state(
        messages=[...],
        mode="autonomous",
        ticket_id="test-123"
    )
    
    final_state = await graph.run(state)
    
    # Verify end-to-end
    assert final_state["ticket_analysis"] is not None
    assert final_state["diagnosis"] is not None
```

## Performance Considerations

### Parallel Execution

The graph supports parallel execution of independent operations:

```python
# Knowledge retrieval and tool planning can run in parallel
# (Future optimization)
```

### Caching

State updates are efficient with immutable operations:

```python
# Only changed fields are updated
new_state = update_state(state, diagnosis="...")
# Original state unchanged, minimal copying
```

### Logging

All nodes log their execution for observability:

```python
logger.info("node_classify_start", ticket_id=state["ticket_id"])
logger.info("node_classify_complete", category=analysis.category)
```

## Troubleshooting

### Graph Execution Fails

**Symptom**: `ProviderError: Graph execution failed`

**Solutions**:
1. Check LLM provider connectivity
2. Verify all required agents are initialized
3. Check state has required fields
4. Review logs for specific node failures

### Approval Mode Not Pausing

**Symptom**: Reply posted without approval

**Solutions**:
1. Verify `mode="approval"` in state
2. Check `ticket_id` is present
3. Ensure `ticket_provider` is configured
4. Verify `_should_post_reply` routing logic

### State Not Updating

**Symptom**: Changes not reflected in final state

**Solutions**:
1. Use `update_state()` helper function
2. Never mutate state directly
3. Return new state from node functions
4. Check node is properly connected in graph

## Future Enhancements

### Tool Execution

Full implementation of tool planning and execution:

```python
# Plan tools based on diagnosis
commands = await tool_agent.plan_execution(state["diagnosis"])

# Execute with approval gate
if state["mode"] == "approval":
    state["pending_approval"] = {"commands": commands}
    return state

# Execute tools
results = await tool_executor.run(commands)
state["tool_results"] = results
```

### User Style Learning

Inject user communication style into responses:

```python
# Retrieve user style context
style_context = await style_injector.get_style_prompt()
state["user_style_context"] = style_context

# Engineer agent uses style in system prompt
```

### Browser Automation

Fallback to browser when API fails:

```python
try:
    await ticket_provider.reply(ticket_id, message)
except APIError:
    if config.USE_BROWSER_FALLBACK:
        await browser_agent.post_reply(ticket_id, message)
```

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [State Management](./state_management.md)
- [Agent Architecture](./architecture.md)
