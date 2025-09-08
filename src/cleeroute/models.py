from typing import List, Optional, Literal,Union
from pydantic import BaseModel, Field
from enum import Enum

class Course_meta_datas_input(BaseModel):
    response: str

    class Config:
        json_schema_extra = {
            "example": {
                "response":"I want to speak english like a native"
            }
        }

class Course_meta_datas(BaseModel):
    title: str 
    domains: List[str] 
    categories: List[str] 
    topics: List[str]
    objectives: List[str]
    expectations: List[str]
    prerequisites: List[str]
    desired_level: str

class CourseInput(Course_meta_datas):
    
    class Config:
        json_schema_extra = {
            "examples": [
            {
                "title": "Achieving Native-Like English Fluency",
                "domains": [
                    "Language Learning"
                ],
                "categories": [
                    "English Language Learning",
                    "Accent Reduction"
                ],
                "topics": [
                    "pronunciation",
                    "speaking skills",
                    "fluency",
                    "conversation practice",
                    "english idioms",
                    "phrasal verbs",
                    "intonation",
                    "rhythm",
                    "stress patterns",
                    "phonetics",
                    "grammar",
                    "vocabulary"
                ],
                "objectives": [
                    "I will develop the ability to speak English with native-like fluency and natural pronunciation.",
                    "I will expand my vocabulary and command of idiomatic expressions to sound more natural and nuanced.",
                    "I will gain confidence in engaging in spontaneous conversations across various topics.",
                    "I will refine my understanding and use of complex grammatical structures in spoken English."
                ],
                "expectations": [
                    "I want to improve my fluency so I don't hesitate when speaking.",
                    "I expect to reduce my foreign accent to sound more natural.",
                    "I anticipate learning and using more natural phrases and idioms.",
                    "I might not yet be comfortable using complex grammatical structures spontaneously.",
                    "I may struggle with understanding fast or informal native speech."
                ],
                "prerequisites": [
                    "Basic understanding of English grammar (e.g., sentence structure, common tenses).",
                    "A foundational English vocabulary (A2/B1 level or equivalent).",
                    "Ability to form simple sentences and convey basic ideas in English.",
                    "Familiarity with the English alphabet and basic pronunciation."
                ],
                "desired_level": "advanced"
            }
        ]
    }

class Project(BaseModel):
    title: str
    description: str
    objectives: List[str]
    prerequisites: List[str]
    Steps: List[str]
    Deliverable: List[str]
    evaluation_criteria: Optional[List[str]] = None


class Subsection(BaseModel):
    title: str
    description: str

class Section(BaseModel):
    title: str
    description: str
    subsections: List[Subsection]
    project: Optional[Project] = None
    
# complete course structure for the humain in the loop action

class CompleteCourse(BaseModel):
    title: str
    introduction: Optional[str] = None
    sections: List[Section]

    class Config:
        json_schema_extra = {
            "examples": [
        {
            "title": "Deep Learning Fundamentals",
            "introduction": "This course provides a comprehensive introduction to deep learning, covering the theoretical foundations, key architectures, and practical applications. Learners will progress from basic concepts to hands-on project work.",
            "sections": [
                {
                "title": "Introduction to Deep Learning",
                "description": "Understand what deep learning is, its history, and its role in modern artificial intelligence.",
                "subsections": [
                    {
                    "title": "What is Deep Learning?",
                    "description": "Definition, scope, and differences with machine learning."
                    },
                    {
                    "title": "History of Neural Networks",
                    "description": "From perceptrons to modern deep neural networks."
                    },
                    {
                    "title": "Applications of Deep Learning",
                    "description": "Explore real-world applications such as computer vision, NLP, and healthcare."
                    }
                ],
                "project": {
                    "title": "Deep Learning Use Case Research",
                    "description": "Learners will research and present a real-world application of deep learning.",
                    "objectives": [
                    "Identify an application domain of deep learning.",
                    "Explain how deep learning is used in this context.",
                    "Analyze the benefits and challenges of this application."
                    ],
                    "prerequisites": ["Basic knowledge of AI and machine learning concepts."],
                    "Steps": [
                    "Choose an industry/domain.",
                    "Research a deep learning application in that domain.",
                    "Prepare a short report and presentation."
                    ],
                    "Deliverable": [
                    "2-page written report.",
                    "5-minute presentation."
                    ],
                    "evaluation_criteria": [
                    "Clarity of explanation.",
                    "Depth of research.",
                    "Relevance of chosen use case."
                    ]
                }
                },
                {
                "title": "Neural Network Basics",
                "description": "Dive into the fundamentals of artificial neural networks, activation functions, and training.",
                "subsections": [
                    {
                    "title": "Artificial Neurons and Perceptrons",
                    "description": "Learn the structure and function of perceptrons as the building blocks of neural networks."
                    },
                    {
                    "title": "Activation Functions",
                    "description": "Explore sigmoid, ReLU, tanh, and their impact on learning."
                    },
                    {
                    "title": "Forward and Backpropagation",
                    "description": "Understand how networks learn using error propagation."
                    }
                ],
                "project": {
                    "title": "Build a Simple Neural Network",
                    "description": "Implement a simple feedforward neural network from scratch.",
                    "objectives": [
                    "Understand matrix multiplications in forward propagation.",
                    "Implement gradient descent and backpropagation.",
                    "Train the network on a toy dataset."
                    ],
                    "prerequisites": [
                    "Basic Python programming.",
                    "Linear algebra fundamentals."
                    ],
                    "Steps": [
                    "Set up the Python environment.",
                    "Implement forward propagation.",
                    "Implement backpropagation.",
                    "Train on XOR dataset."
                    ],
                    "Deliverable": [
                    "Python script implementing the neural network.",
                    "Training results and plots."
                    ],
                    "evaluation_criteria": [
                    "Correctness of implementation.",
                    "Code readability.",
                    "Successful training of the model."
                    ]
                }
                },
                {
                "title": "Convolutional Neural Networks (CNNs)",
                "description": "Explore CNNs for image processing tasks.",
                "subsections": [
                    {
                    "title": "Convolution and Pooling Layers",
                    "description": "Learn how convolution and pooling extract spatial features."
                    },
                    {
                    "title": "CNN Architectures",
                    "description": "Famous models such as LeNet, AlexNet, and ResNet."
                    },
                    {
                    "title": "Applications in Computer Vision",
                    "description": "Image classification, object detection, and segmentation."
                    }
                ],
                "project": {
                    "title": "Image Classification with CNNs",
                    "description": "Train a CNN on the CIFAR-10 dataset for image classification.",
                    "objectives": [
                    "Preprocess image data for training.",
                    "Build and train a CNN with TensorFlow or PyTorch.",
                    "Evaluate model performance with accuracy and loss."
                    ],
                    "prerequisites": [
                    "Basic neural network knowledge.",
                    "Python programming with TensorFlow or PyTorch."
                    ],
                    "Steps": [
                    "Download CIFAR-10 dataset.",
                    "Preprocess images.",
                    "Build CNN architecture.",
                    "Train and evaluate model."
                    ],
                    "Deliverable": [
                    "Notebook with CNN training code.",
                    "Training and validation performance metrics."
                    ],
                    "evaluation_criteria": [
                    "Correct implementation of CNN.",
                    "Accuracy achieved on test set.",
                    "Documentation of code and results."
                    ]
                }
                },
                {
                "title": "Recurrent Neural Networks (RNNs)",
                "description": "Study RNNs and their applications in sequence data.",
                "subsections": [
                    {
                    "title": "RNN Fundamentals",
                    "description": "Understand recurrent connections and hidden states."
                    },
                    {
                    "title": "LSTMs and GRUs",
                    "description": "Learn how these architectures solve the vanishing gradient problem."
                    },
                    {
                    "title": "Applications in NLP",
                    "description": "Text generation, machine translation, and sentiment analysis."
                    }
                ],
                "project": {
                    "title": "Text Generation with LSTM",
                    "description": "Train an LSTM to generate text in the style of Shakespeare.",
                    "objectives": [
                    "Preprocess text data.",
                    "Build and train an LSTM model.",
                    "Generate text samples."
                    ],
                    "prerequisites": [
                    "Understanding of neural networks.",
                    "Basic NLP preprocessing."
                    ],
                    "Steps": [
                    "Download Shakespeare dataset.",
                    "Preprocess text into sequences.",
                    "Train LSTM model.",
                    "Generate text samples."
                    ],
                    "Deliverable": [
                    "Notebook with LSTM implementation.",
                    "Generated text samples."
                    ],
                    "evaluation_criteria": [
                    "Creativity of generated text.",
                    "Correct implementation of LSTM.",
                    "Quality of documentation."
                    ]
                }
                }
            ]
        }

            ]
    }

class ActionType(str, Enum):
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"

class ModificationInstruction(BaseModel):
    action: ActionType
    target_type: str
    section_title_id: Optional[str] = None
    subsection_title_id: Optional[str] = None
    new_title: Optional[str] = None
    new_description: Optional[str] = None

    new_value: Union[str, dict, List[str], None] = None 
    index: Optional[int] = None

class InstructionSet(BaseModel):
    instructions: List[ModificationInstruction]
    requires_human_intervention: bool = Field(
        default=False,
        description="Set to true if the user's request is ambiguous and cannot be converted into a clear list of instructions."
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Explain why human intervention is needed."
    )