[Back to README](./README.md)

- **Agent Chat**: Interactive chat with a selected running agent. It sends a direct query to that agent, shows responses, and can display related market candles for analysis agents.![ALT-TEXT](image/agentchat-1.jpg)
    
- **Agent Wizard**: Form-based editor for agent definitions in system config. You create/update/delete agents, set model/broker/pair, triggers, prompts, tools, and runtime behavior.![ALT-TEXT](image/agentwizard.jpg)
    
- **Bridge Tool**: Agent-to-agent communication tool plugin. It lets one agent call another agent (or multiple configured targets) as callable tool functions.![ALT-TEXT](image/bridgetool.jpg)
    
- **Event Routing**: Rule set that controls how EventBus messages are delivered. It defines which events go to which agents/handlers (including wildcard and template targets).![ALT-TEXT](image/eventrouting.jpg)
    
- **LLM Checker**: Live diagnostics page for testing LLM modules with optional tools. It behaves like a temporary, non-persistent test agent to validate model behavior, tool calls, and errors.![ALT-TEXT](image/llmchecker.jpg)
    
- **Monitor**: Real-time observability view of system activity. It shows categorized events (LLM, tools, bus, data, broker, errors) for debugging and runtime transparency.![ALT-TEXT](image/monitor.jpg)
    
- **System Config**: Central configuration editor for config/system.json5. It defines modules, agents, and core runtime settings used by the backend.![ALT-TEXT](image/systemconfig.jpg)
    
- **Tool Executor**: Manual tool testing interface. It lets you run registered tools directly with chosen context/arguments to verify behavior independent of full agent cycles. ![ALT-TEXT](image/toolexecutor.jpg)