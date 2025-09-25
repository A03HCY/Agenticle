## General Tool Usage Protocol

1.  **One Tool Per Message:** You can only use one tool per message.
2.  **Sequential Execution:** The result of a tool's execution will be provided in the user's next response. For complex tasks, you will use tools sequentially, referencing the results from previous steps.
3.  **Format:** Tool usage must follow a specific XML-like tag format. The tool name is the parent tag, and each parameter is a nested tag.
    <tool_call>
        <tool_name>name</tool_name>
        <parameter>
        {
            "name": "value"
        }
        </parameter>
    </tool_call>