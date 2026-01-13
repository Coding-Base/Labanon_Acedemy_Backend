"""
Math Formatting Utilities for CBT Backend

Provides helper functions for converting simple math notation to LaTeX
format for proper rendering in the frontend.
"""

import re
from typing import List, Tuple


def convert_to_latex(text: str) -> str:
    """
    Convert simple math notation to LaTeX format.
    
    Examples:
        3x^2 -> 3x^{2}
        sqrt(x) -> \\sqrt{x}
        1/2 -> \\frac{1}{2}
        x_1 -> x_{1}
    
    Args:
        text: The text to convert
        
    Returns:
        Text with LaTeX formatting applied
    """
    if not text:
        return text
    
    result = text
    
    # Convert powers: x^2 -> x^{2}, x^n -> x^{n}
    result = re.sub(r'\^(\d+)', r'^{\1}', result)
    result = re.sub(r'\^([a-zA-Z])', r'^{\1}', result)
    
    # Convert square root: sqrt(x) -> \sqrt{x}
    result = re.sub(r'sqrt\(([^)]+)\)', r'\\sqrt{\1}', result)
    
    # Convert fractions: 1/2 -> \frac{1}{2}
    result = re.sub(r'(\d+)/(\d+)', r'\\frac{\1}{\2}', result)
    
    # Convert subscripts: x_1 -> x_{1}, x_n -> x_{n}
    result = re.sub(r'_(\d+)', r'_{\1}', result)
    result = re.sub(r'_([a-zA-Z])', r'_{\1}', result)
    
    return result


def has_math_notation(text: str) -> bool:
    """
    Check if text contains mathematical notation.
    
    Args:
        text: The text to check
        
    Returns:
        True if text contains common math patterns
    """
    if not text:
        return False
    
    math_patterns = [
        r'\^',           # Power (original or converted)
        r'\{',           # Braces (converted LaTeX)
        r'\}',           # Braces (converted LaTeX)
        r'sqrt',         # Square root (original or \sqrt in LaTeX)
        r'frac',         # Fraction command
        r'[0-9]/[0-9]',  # Fraction
        r'_',            # Subscript
        r'\\[a-z]',      # LaTeX command
        r'\$',           # LaTeX delimiters
    ]
    
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in math_patterns)


def wrap_in_math(text: str) -> str:
    """
    Wrap text in LaTeX inline math delimiters if needed.
    
    Args:
        text: The text to wrap
        
    Returns:
        Text wrapped in $ delimiters if it contains math notation
    """
    if not text or (text.startswith('$') and text.endswith('$')):
        return text
    
    if has_math_notation(text):
        return f'${text}$'
    
    return text


def format_math_question(question_text: str) -> str:
    """
    Format a mathematical question for display.
    
    Combines multiple utilities to prepare a question for rendering.
    
    Args:
        question_text: The question text
        
    Returns:
        Formatted question text ready for KaTeX rendering
    """
    if not question_text:
        return ''
    
    # Check if original text has math notation
    has_math = has_math_notation(question_text)
    
    if has_math:
        # Convert to LaTeX
        formatted = convert_to_latex(question_text)
        # Wrap in $ delimiters if not already wrapped
        if not (formatted.startswith('$') and formatted.endswith('$')):
            formatted = f'${formatted}$'
        return formatted
    
    return question_text


def format_math_choices(choices: List[str]) -> List[str]:
    """
    Format an array of answer choices.
    
    Args:
        choices: List of choice texts
        
    Returns:
        List of formatted choice texts
    """
    return [format_math_question(choice) for choice in choices]


def extract_math_expressions(text: str) -> List[str]:
    """
    Extract all mathematical expressions from text.
    
    Args:
        text: The text to search
        
    Returns:
        List of math expressions found
    """
    if not text:
        return []
    
    expressions = []
    
    # Extract inline math: $...$
    inline_math = re.findall(r'\$([^$]+)\$', text)
    expressions.extend(inline_math)
    
    # Extract block math: $$...$$
    block_math = re.findall(r'\$\$([^$]+)\$\$', text)
    expressions.extend(block_math)
    
    # Extract LaTeX inline: \(...\)
    latex_inline = re.findall(r'\\\(([^\)]+)\\\)', text)
    expressions.extend(latex_inline)
    
    # Extract LaTeX block: \[...\]
    latex_block = re.findall(r'\\\[([^\]]+)\\\]', text)
    expressions.extend(latex_block)
    
    return expressions


def is_valid_latex(latex: str) -> bool:
    """
    Validate LaTeX syntax (basic check).
    
    Checks for balanced braces.
    
    Args:
        latex: LaTeX string to validate
        
    Returns:
        True if LaTeX appears to be valid
    """
    if not latex:
        return False
    
    brace_count = 0
    for char in latex:
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
        
        if brace_count < 0:
            return False
    
    return brace_count == 0


def replace_symbols(text: str) -> str:
    """
    Replace common symbol names with LaTeX equivalents.
    
    Examples:
        "pi" -> "\\pi"
        "sqrt2" -> "\\sqrt{2}"
        "infinity" -> "\\infty"
    
    Args:
        text: Text containing symbol names
        
    Returns:
        Text with symbols replaced by LaTeX
    """
    if not text:
        return text
    
    symbols = {
        'pi': r'\pi',
        'sqrt2': r'\sqrt{2}',
        'sqrt3': r'\sqrt{3}',
        'infinity': r'\infty',
        'alpha': r'\alpha',
        'beta': r'\beta',
        'gamma': r'\gamma',
        'delta': r'\delta',
        'theta': r'\theta',
        'lambda': r'\lambda',
        'mu': r'\mu',
        'sigma': r'\sigma',
        'sum': r'\sum',
        'integral': r'\int',
        'approx': r'\approx',
        'neq': r'\neq',
        'leq': r'\leq',
        'geq': r'\geq',
        'pm': r'\pm',
        'degree': r'^\circ',
    }
    
    result = text
    
    for name, latex in symbols.items():
        pattern = r'\b' + re.escape(name) + r'\b'
        result = re.sub(pattern, latex, result, flags=re.IGNORECASE)
    
    return result


def batch_format_questions(questions: List[dict]) -> List[dict]:
    """
    Format a batch of questions with math notation.
    
    Args:
        questions: List of question dictionaries with 'text' and 'choices' keys
        
    Returns:
        List of formatted questions
    """
    formatted_questions = []
    
    for question in questions:
        formatted_q = {
            **question,
            'text': format_math_question(question.get('text', '')),
        }
        
        if 'choices' in question:
            formatted_q['choices'] = format_math_choices(question['choices'])
        
        if 'options' in question:
            # For questions with options dict (A, B, C, D)
            formatted_q['options'] = {
                key: format_math_question(value)
                for key, value in question['options'].items()
            }
        
        formatted_questions.append(formatted_q)
    
    return formatted_questions
