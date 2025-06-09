from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from .models import Course, Course_meta_datas
import os
from crewai_tools import SerperDevTool, WebsiteSearchTool
import os
from dotenv import load_dotenv
load_dotenv() 

# =================================== Meta data Crew ===========================
@CrewBase
class Course_meta_datas_crew():
    """Course_meta_datas_crew crew"""
    agents_config = 'config/agents_2.yaml'
    tasks_config = 'config/tasks_2.yaml'

    @agent
    def Meta_data_courses_researcher(self)->Agent:
        return Agent(
            config= self.agents_config["Meta_data_courses_researcher"],
        )
    
    @task
    def Meta_data_courses_researcher_task(self)->Task:
        return Task(
            config= self.tasks_config["Meta_data_courses_researcher_task"],
            output_json = Course_meta_datas
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Course_meta_datas_crew crew"""
        return Crew(
            agents=self.agents, 
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
    
# ================================== Course structure Crew =====================

@CrewBase
class Course_structure_crew():
    """Course_structure_crew crew"""
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    ### Buildings agents
    @agent
    def Company_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['Company_researcher'],
            verbose=True
        )

    @agent
    def Course_planner(self) -> Agent:
        return Agent(
            config=self.agents_config['Course_planner'],
            verbose=True
        )

    @agent
    def project_builder(self) -> Agent:
        return Agent(
            config=self.agents_config['project_builder'],
            verbose=True
        )
    
    @agent
    def Course_compiler(self) -> Agent:
        return Agent(
            config=self.agents_config['Course_compiler'],
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
    def project_builder_task(self) -> Task:
        return Task(
            config=self.tasks_config['project_builder_task'],
        )
    
    @task
    def Course_compiler_task(self) -> Task:
        return Task(
            config=self.tasks_config['Course_compiler_task'],
            output_json= Course,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Course_structure_crew crew"""
        return Crew(
            agents=self.agents, 
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )