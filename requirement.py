from agenticle import Agent


agent = Agent(
    name='test',
    description=''
)

agents: list[Agent] = agent * 5

print(agents)