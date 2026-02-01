"""Mock Question Generation Service for MVP testing."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class QuestionType(str, Enum):
    """Types of interview questions."""
    INTRODUCTION = "introduction"
    BEHAVIORAL = "behavioral"
    SITUATIONAL = "situational"
    TECHNICAL = "technical"
    CLOSING = "closing"


@dataclass
class InterviewQuestion:
    """Represents an interview question."""
    id: int
    text: str
    type: QuestionType
    follow_up_hint: Optional[str] = None


# 10 Mixed Interview Questions for a realistic demo flow
MOCK_QUESTIONS: list[InterviewQuestion] = [
    # Introduction (1)
    InterviewQuestion(
        id=1,
        text="Hello! Welcome to this interview. Let's start with a brief introduction. Could you please tell me about yourself and your professional background?",
        type=QuestionType.INTRODUCTION,
        follow_up_hint="Listen for experience level and key skills",
    ),
    
    # Behavioral (2-4)
    InterviewQuestion(
        id=2,
        text="That's great to hear. Now, can you tell me about a challenging project you worked on? What was your role, and how did you handle the challenges?",
        type=QuestionType.BEHAVIORAL,
        follow_up_hint="Look for problem-solving approach",
    ),
    InterviewQuestion(
        id=3,
        text="Excellent. Describe a time when you had to work with a difficult team member. How did you handle the situation, and what was the outcome?",
        type=QuestionType.BEHAVIORAL,
        follow_up_hint="Assess interpersonal skills",
    ),
    InterviewQuestion(
        id=4,
        text="Can you share an example of when you had to learn a new skill or technology quickly? How did you approach the learning process?",
        type=QuestionType.BEHAVIORAL,
        follow_up_hint="Evaluate adaptability and learning agility",
    ),
    
    # Situational (5-6)
    InterviewQuestion(
        id=5,
        text="Imagine you're given a project with an unrealistic deadline. How would you handle this situation with your manager and team?",
        type=QuestionType.SITUATIONAL,
        follow_up_hint="Check communication and negotiation skills",
    ),
    InterviewQuestion(
        id=6,
        text="If you discovered a critical bug in production right before a major release, what steps would you take to address it?",
        type=QuestionType.SITUATIONAL,
        follow_up_hint="Assess crisis management and prioritization",
    ),
    
    # Technical/Role-specific (7-8)
    InterviewQuestion(
        id=7,
        text="What's your approach to ensuring quality in your work? Can you walk me through your process for reviewing or testing your deliverables?",
        type=QuestionType.TECHNICAL,
        follow_up_hint="Evaluate attention to detail and quality standards",
    ),
    InterviewQuestion(
        id=8,
        text="How do you stay updated with the latest trends and best practices in your field? Can you give a recent example?",
        type=QuestionType.TECHNICAL,
        follow_up_hint="Check continuous learning attitude",
    ),
    
    # Behavioral (9)
    InterviewQuestion(
        id=9,
        text="Tell me about a time when you received constructive criticism. How did you respond, and what did you learn from it?",
        type=QuestionType.BEHAVIORAL,
        follow_up_hint="Assess self-awareness and growth mindset",
    ),
    
    # Closing (10)
    InterviewQuestion(
        id=10,
        text="We're coming to the end of our interview. What questions do you have for me about the role or the company?",
        type=QuestionType.CLOSING,
        follow_up_hint="Final question - wrap up interview",
    ),
]


class MockQuestionService:
    """
    Mock service that simulates the Question Generation Service.
    
    For MVP testing, this returns predefined questions.
    In production, this will be replaced with the actual service integration.
    """

    def __init__(self):
        self.questions = MOCK_QUESTIONS
        self._current_question_index: dict[str, int] = {}  # session_id -> index

    def start_session(self, session_id: str) -> None:
        """Initialize a new interview session."""
        self._current_question_index[session_id] = 0

    def get_next_question(
        self, 
        session_id: str, 
        previous_answer: Optional[str] = None
    ) -> Optional[InterviewQuestion]:
        """
        Get the next question for the session.
        
        In the mock implementation, we ignore the previous_answer.
        The real service would use it to generate contextual follow-ups.
        
        Args:
            session_id: The interview session ID
            previous_answer: The user's answer to the previous question (unused in mock)
            
        Returns:
            The next InterviewQuestion or None if interview is complete
        """
        if session_id not in self._current_question_index:
            self.start_session(session_id)

        current_index = self._current_question_index[session_id]
        
        if current_index >= len(self.questions):
            return None  # Interview complete
        
        question = self.questions[current_index]
        self._current_question_index[session_id] = current_index + 1
        
        return question

    def get_question_by_id(self, question_id: int) -> Optional[InterviewQuestion]:
        """Get a specific question by its ID."""
        for q in self.questions:
            if q.id == question_id:
                return q
        return None

    def get_total_questions(self) -> int:
        """Get the total number of questions in the interview."""
        return len(self.questions)

    def get_progress(self, session_id: str) -> tuple[int, int]:
        """
        Get the current progress in the interview.
        
        Returns:
            Tuple of (current_question_number, total_questions)
        """
        current = self._current_question_index.get(session_id, 0)
        return (current, len(self.questions))

    def is_interview_complete(self, session_id: str) -> bool:
        """Check if the interview is complete for a session."""
        current = self._current_question_index.get(session_id, 0)
        return current >= len(self.questions)

    def end_session(self, session_id: str) -> None:
        """Clean up session data."""
        if session_id in self._current_question_index:
            del self._current_question_index[session_id]
