# workouts/ai_generator.py
import os
import json
from openai import OpenAI
# Alternative: import google.generativeai as genai

from .models import Exercise


class AIWorkoutGenerator:
    """
    Generate personalized workouts using AI (OpenAI GPT or Google Gemini).

    Usage:
        generator = AIWorkoutGenerator()
        workout = generator.generate_workout(
            user_profile={'fitness_level': 'intermediate', 'goals': 'build muscle'},
            preferences={'duration': 60, 'equipment': ['barbell', 'dumbbell']}
        )
    """

    def __init__(self, provider='openai'):
        """
        Initialize AI client.

        Args:
            provider (str): 'openai' or 'gemini'
        """
        self.provider = provider

        if provider == 'openai':
            self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            self.model = "gpt-4o-mini"  # Cost-effective, fast
        elif provider == 'gemini':
            # For Gemini implementation
            import google.generativeai as genai
            genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
            self.client = genai.GenerativeModel('gemini-pro')
        else:
            raise ValueError("Provider must be 'openai' or 'gemini'")

    def generate_workout(self, user_profile, preferences, available_exercises=None):
        """
        Generate a personalized workout plan.

        Args:
            user_profile (dict): User info (fitness_level, goals, injuries, etc.)
            preferences (dict): Workout preferences (duration, focus, equipment)
            available_exercises (list): Optional list of Exercise objects to choose from

        Returns:
            dict: Structured workout plan with exercises, sets, reps
        """
        # Get available exercises from database
        if available_exercises is None:
            available_exercises = Exercise.objects.filter(is_official=True)

        # Build exercise library context
        exercise_library = self._format_exercise_library(available_exercises, preferences.get('equipment'))

        # Build the prompt
        prompt = self._build_prompt(user_profile, preferences, exercise_library)

        # Generate workout using selected AI provider
        if self.provider == 'openai':
            response = self._generate_with_openai(prompt)
        else:
            response = self._generate_with_gemini(prompt)

        # Parse and validate response
        workout_plan = self._parse_response(response)

        return workout_plan

    def _build_prompt(self, user_profile, preferences, exercise_library):
        """Build the AI prompt with context."""

        fitness_level = user_profile.get('fitness_level', 'beginner')
        goals = user_profile.get('goals', 'general fitness')
        injuries = user_profile.get('injuries', 'none')
        experience = user_profile.get('experience_years', 0)

        duration = preferences.get('duration', 60)
        focus_areas = preferences.get('focus_areas', ['full body'])
        equipment = preferences.get('equipment', ['all available'])
        workout_type = preferences.get('type', 'strength')  # strength, hypertrophy, endurance

        prompt = f"""You are an expert fitness coach. Create a personalized workout plan based on the following:

USER PROFILE:
- Fitness Level: {fitness_level}
- Goals: {goals}
- Experience: {experience} years
- Injuries/Limitations: {injuries}

WORKOUT PREFERENCES:
- Duration: {duration} minutes
- Focus Areas: {', '.join(focus_areas)}
- Available Equipment: {', '.join(equipment)}
- Workout Type: {workout_type}

AVAILABLE EXERCISES:
{exercise_library}

INSTRUCTIONS:
1. Select 5-8 exercises from the AVAILABLE EXERCISES list only
2. Create a balanced workout targeting the requested focus areas
3. Consider the user's fitness level when prescribing sets, reps, and weights
4. Include warm-up exercises if appropriate
5. Provide rest periods between sets
6. Add coaching notes for proper form and safety

RESPONSE FORMAT (JSON):
{{
    "workout_name": "Descriptive workout name",
    "description": "Brief overview of the workout",
    "estimated_duration": 60,
    "warm_up_notes": "Warm-up recommendations",
    "exercises": [
        {{
            "exercise_id": 1,
            "exercise_name": "Exercise name from available list",
            "order": 1,
            "target_sets": 3,
            "target_reps": "8-12",
            "rest_seconds": 90,
            "notes": "Form cues and coaching tips",
            "starting_weight_suggestion": "Start with bodyweight/light weight"
        }}
    ],
    "cool_down_notes": "Cool-down and stretching recommendations"
}}

Respond ONLY with valid JSON, no additional text."""

        return prompt

    def _format_exercise_library(self, exercises, equipment_filter=None):
        """Format exercise library for the prompt."""

        # Filter by equipment if specified
        if equipment_filter:
            exercises = exercises.filter(equipment__in=equipment_filter)

        exercise_text = []
        for ex in exercises[:50]:  # Limit to avoid token limits
            exercise_text.append(
                f"ID: {ex.id} | Name: {ex.name} | Equipment: {ex.equipment} | "
                f"Muscles: {', '.join(ex.muscle_groups)} | Difficulty: {ex.difficulty}"
            )

        return "\n".join(exercise_text)

    def _generate_with_openai(self, prompt):
        """Generate workout using OpenAI GPT."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert fitness coach and personal trainer with 15+ years of experience. You create safe, effective, personalized workout plans."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,  # Some creativity but mostly consistent
                max_tokens=2000,
                response_format={"type": "json_object"}  # Force JSON response
            )

            return response.choices[0].message.content

        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")

    def _generate_with_gemini(self, prompt):
        """Generate workout using Google Gemini."""

        try:
            response = self.client.generate_content(prompt)
            return response.text

        except Exception as e:
            raise Exception(f"Gemini API error: {str(e)}")

    def _parse_response(self, response_text):
        """Parse and validate AI response."""

        try:
            # Clean response (remove markdown code blocks if present)
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]

            workout_plan = json.loads(response_text.strip())

            # Validate required fields
            required_fields = ['workout_name', 'exercises']
            for field in required_fields:
                if field not in workout_plan:
                    raise ValueError(f"Missing required field: {field}")

            # Validate exercises
            if not workout_plan['exercises']:
                raise ValueError("No exercises in workout plan")

            for exercise in workout_plan['exercises']:
                if 'exercise_id' not in exercise:
                    raise ValueError("Exercise missing exercise_id")

            return workout_plan

        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse AI response as JSON: {str(e)}")
        except Exception as e:
            raise ValueError(f"Invalid workout plan structure: {str(e)}")

    def regenerate_with_feedback(self, original_workout, feedback):
        """
        Regenerate workout based on user feedback.

        Args:
            original_workout (dict): The original generated workout
            feedback (str): User's feedback (e.g., "too hard", "need more cardio")

        Returns:
            dict: Modified workout plan
        """

        prompt = f"""You previously generated this workout:
{json.dumps(original_workout, indent=2)}

The user provided this feedback: "{feedback}"

Please modify the workout to address their feedback while maintaining the same general structure.
Respond ONLY with the updated workout plan in JSON format."""

        if self.provider == 'openai':
            response = self._generate_with_openai(prompt)
        else:
            response = self._generate_with_gemini(prompt)

        return self._parse_response(response)


# Utility function for quick workout generation
def generate_ai_workout(user, preferences):
    """
    Convenience function to generate workout for a user.

    Args:
        user (User): Django user object
        preferences (dict): Workout preferences

    Returns:
        dict: Generated workout plan
    """
    # Build user profile from User and Profile models
    profile = user.profile

    user_profile = {
        'fitness_level': preferences.get('fitness_level', 'intermediate'),
        'goals': preferences.get('goals', 'build muscle and strength'),
        'injuries': preferences.get('injuries', 'none'),
        'experience_years': profile.years_experience or 0,
    }

    # Initialize generator (use environment variable to switch providers)
    provider = os.getenv('AI_PROVIDER', 'openai')  # 'openai' or 'gemini'
    generator = AIWorkoutGenerator(provider=provider)

    # Generate workout
    workout_plan = generator.generate_workout(user_profile, preferences)

    return workout_plan