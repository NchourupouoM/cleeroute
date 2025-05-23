from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from .models import Course
import os
from crewai_tools import SerperDevTool, WebsiteSearchTool
import os
from dotenv import load_dotenv
load_dotenv() 

serper_dev_tool = SerperDevTool()
web_dev_tool = WebsiteSearchTool()

# llm = LLM(
#     model='gemini/gemini-2.0-flash',
#     api_key=os.environ["GEMINI_API_KEY"]
# )

@CrewBase
class Cleeroute():
    """Cleeroute crew"""
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    ### Buildings agents
    @agent
    def Company_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['Company_researcher'],
            tools=[serper_dev_tool,web_dev_tool],
            # llm=llm,
            verbose=True
        )

    @agent
    def Course_planner(self) -> Agent:
        return Agent(
            config=self.agents_config['Course_planner'],
            tools=[serper_dev_tool,web_dev_tool],
            # llm= llm,
            verbose=True
        )

    @agent
    def quiz_builder(self) -> Agent:
        return Agent(
            config=self.agents_config['quiz_builder'],
            tools=[serper_dev_tool,web_dev_tool],
            # llm=llm,
            verbose=True
        )

    @agent
    def project_builder(self) -> Agent:
        return Agent(
            config=self.agents_config['project_builder'],
            tools=[serper_dev_tool,web_dev_tool],
            # llm=llm,
            verbose=True
        )
    
    @agent
    def Course_compiler(self) -> Agent:
        return Agent(
            config=self.agents_config['Course_compiler'],
            tools=[serper_dev_tool,web_dev_tool],
            # llm=llm,
            verbose=True
        )

    ### Building task
    @task
    def Company_researcher_task(self) -> Task:
        return Task(
            config=self.tasks_config['Company_researcher_task'],
        )
    
    @task
    def Course_planner_task(self) -> Task:
        return Task(
            config=self.tasks_config['Course_planner_task'],
        )
    
    @task
    def Quiz_builder_task(self) -> Task:
        return Task(
            config=self.tasks_config['Quiz_builder_task'],
        )
    
    @task
    def project_builder_task(self) -> Task:
        return Task(
            config=self.tasks_config['project_builder_task'],
        )
    
    @task
    def Course_compiler_task(self) -> Task:
        return Task(
            config=self.tasks_config['Course_compiler_task'],
            output_pydantic= Course,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Cleeroute crew"""
        return Crew(
            agents=self.agents, 
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )