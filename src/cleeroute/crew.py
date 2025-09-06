# from crewai import Agent, Crew, Process, Task
# from crewai.project import CrewBase, agent, crew, task
# from .models import Course, Course_meta_datas
# import os

# # =================================== Meta data Crew ===========================
# @CrewBase
# class Course_meta_datas_crew():
#     """Course_meta_datas_crew crew"""
#     agents_config = 'config/agents_2.yaml'
#     tasks_config = 'config/tasks_2.yaml'

#     @agent
#     def Meta_data_courses_researcher(self)->Agent:
#         return Agent(
#             config= self.agents_config["Meta_data_courses_researcher"],
#         )
    
#     @task
#     def Meta_data_courses_researcher_task(self)->Task:
#         return Task(
#             config= self.tasks_config["Meta_data_courses_researcher_task"],
#             output_json = Course_meta_datas
#         )

#     @crew
#     def crew(self) -> Crew:
#         """Creates the Course_meta_datas_crew crew"""
#         return Crew(
#             agents=self.agents, 
#             tasks=self.tasks,
#             process=Process.sequential,
#             verbose=True,
#         )
    
# # ================================== Course structure Crew =====================

# @CrewBase
# class Course_structure_crew():
#     """Course_structure_crew crew"""
#     agents_config = 'config/agents.yaml'
#     tasks_config = 'config/tasks.yaml'

#     ### Buildings agents
#     @agent
#     def Comprehensive_Course_Architect(self) -> Agent:
#         return Agent(
#             config=self.agents_config['Comprehensive_Course_Architect'],
#             verbose=True
#         )
    
#     @agent
#     def Lead_Curriculum_Finalizer(self) -> Agent:
#         return Agent(
#             config=self.agents_config['Lead_Curriculum_Finalizer'],
#             verbose=True
#         )

#     ### Building task
#     @task
#     def Design_Industry_Informed_Course(self) -> Task:
#         return Task(
#             config=self.tasks_config['Design_Industry_Informed_Course'],
#         )
    
#     @task
#     def Finalize_Comprehensive_Course_Package(self) -> Task:
#         return Task(
#             config=self.tasks_config['Finalize_Comprehensive_Course_Package'],
#             output_json= Course,
#         )

#     @crew
#     def crew(self) -> Crew:
#         """Creates the Course_structure_crew crew"""
#         return Crew(
#             agents=self.agents, 
#             tasks=self.tasks,
#             process=Process.sequential,
#             verbose=True,
#         )