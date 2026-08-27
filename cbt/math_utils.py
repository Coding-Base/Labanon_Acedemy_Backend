"""
Math & Chemistry Formatting Utilities for CBT Backend

Provides helper functions for converting simple math and chemistry notation
to LaTeX format for proper rendering in the frontend via KaTeX.

IMPORTANT: This module must be backward-compatible with existing questions
that may already contain LaTeX delimiters ($...$, $$...$$).
"""

import re
from typing import List, Tuple


# ============================================================
# Common chemical formulas for auto-detection
# ============================================================
CHEMICAL_FORMULAS = [
    # Common compounds (sorted longest-first to prevent partial matches)
    'Ca(OH)2', 'Mg(OH)2', 'Al(OH)3', 'Fe(OH)3', 'Cu(OH)2',
    'Na2CO3', 'CaCO3', 'NaHCO3', 'K2CO3', 'MgCO3',
    'H2SO4', 'Na2SO4', 'CuSO4', 'FeSO4', 'MgSO4', 'ZnSO4', 'K2SO4', 'BaSO4',
    'HNO3', 'NaNO3', 'KNO3', 'AgNO3', 'Ca(NO3)2',
    'Na2O', 'CaO', 'MgO', 'Al2O3', 'Fe2O3', 'Fe3O4', 'CO2', 'SO2', 'SO3', 'NO2', 'P2O5',
    'NaCl', 'KCl', 'CaCl2', 'HCl', 'FeCl3', 'FeCl2', 'AlCl3', 'MgCl2', 'NH4Cl', 'ZnCl2',
    'NaOH', 'KOH',
    'H2O2', 'H2O',
    'NH3', 'NH4',
    'CH3COOH', 'C2H5OH', 'CH3OH', 'C6H12O6', 'C12H22O11', 'C2H4', 'C2H2', 'CH4',
    'C6H6', 'C3H8', 'C4H10', 'C2H6',
    'KMnO4', 'K2Cr2O7', 'K2MnO4',
    'PbO2', 'PbO', 'MnO2', 'SiO2', 'TiO2',
    'Na2S', 'H2S', 'FeS', 'FeS2', 'ZnS', 'CuS', 'PbS',
    'NaF', 'KF', 'CaF2', 'HF',
    'KBr', 'NaBr', 'HBr',
    'KI', 'NaI', 'HI',
    'Na', 'Mg', 'Al', 'Si', 'Cl', 'Ar', 'Ca', 'Fe', 'Cu', 'Zn', 'Ag', 'Au', 'Pb', 'Sn',
    'O2', 'N2', 'H2', 'F2', 'Cl2', 'Br2', 'I2',
]

CHEMICAL_LIKE_PATTERN = re.compile(
    r'^[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*(?:\([A-Z][a-z]?\d*\)\d*)*$'
)


def sanitize_escaped_latex(text: str) -> str:
    """
    Repair string escaping errors where backslashes were converted to control characters.
    e.g. \\f (form feed \\x0c), \\b (backspace \\x08), \\v (vertical tab \\x0b).
    """
    if not text:
        return text
    
    # Repair form feed (\x0c) -> \f
    text = text.replace('\x0crac', r'\frac')
    text = text.replace('\x0car', r'\bar')
    text = text.replace('\x0c', r'\f')
    
    # Repair backspace (\x08) -> \b
    text = text.replace('\x08ar', r'\bar')
    text = text.replace('\x08eta', r'\beta')
    text = text.replace('\x08', r'\b')
    
    # Repair vertical tab (\x0b) -> \v
    text = text.replace('\x0b', r'\v')
    
    return text


def is_chemical_formula(text: str) -> bool:
    """
    Check if a string looks like a chemical formula.
    
    Examples that match: H2O, NaCl, H2SO4, Ca(OH)2, C6H12O6, O2, Fe2O3
    Examples that don't match: Hello, World, ISBN, PDF, ABC
    """
    text = text.strip()
    if not text or len(text) < 2:
        return False
    
    if text in CHEMICAL_FORMULAS:
        return True
    
    if CHEMICAL_LIKE_PATTERN.match(text) and re.search(r'\d', text):
        return True
    
    return False


def format_chemical_formula(formula: str) -> str:
    """Convert a chemical formula to LaTeX using \\ce{} notation."""
    return '$\\ce{' + str(formula) + '}$'


def convert_reaction_arrows(text: str) -> str:
    """Convert common reaction arrow notations to LaTeX."""
    text = re.sub(r'\s*<\s*=\s*>\s*', r' $\\rightleftharpoons$ ', text)
    text = re.sub(r'\s*<\s*-\s*>\s*', r' $\\rightleftharpoons$ ', text)
    text = re.sub(r'\s*⇌\s*', r' $\\rightleftharpoons$ ', text)
    text = re.sub(r'\s*-\s*-\s*>\s*', r' $\\rightarrow$ ', text)
    text = re.sub(r'\s*-\s*>\s*', r' $\\rightarrow$ ', text)
    text = re.sub(r'\s*→\s*', r' $\\rightarrow$ ', text)
    return text


def convert_scientific_notation(text: str) -> str:
    """Convert scientific notation patterns to LaTeX."""
    text = re.sub(
        r'(\d+\.?\d*)\s*[x×\*]\s*10\s*\^\s*\{?\s*(-?\d+)\s*\}?',
        r'$\1 \\times 10^{\2}$',
        text
    )
    text = re.sub(
        r'(\d+\.?\d*)\s*[eE]\s*(-?\d+)',
        r'$\1 \\times 10^{\2}$',
        text
    )
    return text


def convert_ionic_charges(text: str) -> str:
    """Convert ionic charge notation to LaTeX."""
    text = re.sub(
        r'\b([A-Z][a-z]?(?:\d*))\s*\^\s*(\d*[+-])',
        lambda m: '$\\text{' + m.group(1) + '}^{' + m.group(2) + '}$',
        text
    )
    return text


def convert_to_latex(text: str) -> str:
    """
    Convert simple math notation to LaTeX format.
    Only converts math syntax markers, does not wrap in delimiters.
    """
    if not text:
        return text
    
    result = text
    
    # If it's already a full LaTeX command like \frac{a}{b} or \bar{x}, keep intact
    if result.startswith('\\'):
        return result
    
    # Convert powers: x^2 -> x^{2}, x^n -> x^{n}
    result = re.sub(r'\^(\d+)', r'^{\1}', result)
    result = re.sub(r'\^([a-zA-Z])', r'^{\1}', result)
    
    # Convert square root: sqrt(x) -> \sqrt{x}
    result = re.sub(r'sqrt\(([^)]+)\)', r'\\sqrt{\1}', result)
    
    # Convert fractions: 1/2 -> \frac{1}{2} (only numeric fractions)
    result = re.sub(r'(\d+)/(\d+)', r'\\frac{\1}{\2}', result)
    
    # Convert subscripts: x_1 -> x_{1}, x_n -> x_{n}
    result = re.sub(r'_(\d+)', r'_{\1}', result)
    result = re.sub(r'_([a-zA-Z])', r'_{\1}', result)
    
    return result


def has_math_notation(text: str) -> bool:
    """
    Check if a segment contains mathematical notation or LaTeX commands.
    """
    if not text:
        return False
    
    math_patterns = [
        r'\^{',             # Already-converted LaTeX power
        r'_{',              # Already-converted LaTeX subscript
        r'\\sqrt',          # LaTeX sqrt
        r'\\frac',          # LaTeX fraction
        r'\\bar',           # LaTeX overline/bar
        r'\\ce',            # mhchem chemistry command
        r'\\text',          # LaTeX text
        r'\\times',         # LaTeX multiplication
        r'\\div',           # LaTeX division
        r'\\pm',            # LaTeX plus-minus
        r'\\alpha|\\beta|\\gamma|\\delta|\\theta|\\pi|\\sigma|\\lambda|\\mu|\\Delta', # Greek
        r'\w\^\d',          # Power notation: x^2
        r'\w\^[a-zA-Z]',   # Power notation: x^n
        r'\w_\d',           # Subscript: x_1
        r'sqrt\(',          # sqrt function
        r'\d+/\d+',         # Numeric fraction
        r'\\[a-z]+{',       # Generic LaTeX command with argument
    ]
    
    return any(re.search(pattern, text) for pattern in math_patterns)


def smart_wrap_math_segments(text: str) -> str:
    """
    Intelligently wrap only math segments in LaTeX delimiters.
    Leaves English sentences untouched.
    """
    if not text:
        return ''
    
    # Sanitize control character escapes
    text = sanitize_escaped_latex(text)
    
    # If text already has $ delimiters, it's already formatted — pass through
    if '$' in text:
        return text
    
    # Handle reaction arrows
    text = convert_reaction_arrows(text)
    
    # Handle scientific notation
    text = convert_scientific_notation(text)
    
    # Handle ionic charges
    text = convert_ionic_charges(text)
    
    # Tokenize and process word by word
    return _process_remaining_math(text)


def _process_remaining_math(text: str) -> str:
    """Process text that may have some $ delimiters already added."""
    parts = re.split(r'(\$[^$]+\$|\$\$[^$]+\$\$)', text)
    result_parts = []
    
    for part in parts:
        if not part:
            continue
        if part.startswith('$'):
            result_parts.append(part)
            continue
        result_parts.append(_wrap_segment_math(part))
    
    return ''.join(result_parts)


def _wrap_segment_math(text: str) -> str:
    """
    Process a text segment to wrap math expressions and chemical formulas in $...$.
    CRITICAL: Never strip braces '{' or '}' as they belong to LaTeX commands like \\frac{27}{100}.
    """
    tokens = re.split(r'(\s+)', text)
    result_tokens = []
    
    for token in tokens:
        if not token or token.isspace():
            result_tokens.append(token)
            continue
        
        # Strip sentence punctuation only (commas, periods, semicolons, quotes, question marks)
        # Preserve curly braces {}, brackets [], and parentheses if inside LaTeX!
        if '\\' in token:
            # Token contains LaTeX command: strip only leading/trailing sentence punctuation
            stripped = token.strip('.,;:!?"\'')
            leading = token[:len(token) - len(token.lstrip('.,;:!?"\''))]
            trailing = token[len(stripped) + len(leading):]
        else:
            stripped = token.strip('.,;:!?"\'()')
            leading = token[:len(token) - len(token.lstrip('.,;:!?"\'()'))]
            trailing = token[len(stripped) + len(leading):]
        
        # Check if it's a known chemical formula
        if is_chemical_formula(stripped):
            result_tokens.append(leading + '$\\ce{' + stripped + '}$' + trailing)
        # Check if it contains math notation or LaTeX command
        elif has_math_notation(stripped):
            converted = convert_to_latex(stripped)
            result_tokens.append(leading + '$' + converted + '$' + trailing)
        else:
            result_tokens.append(token)
    
    return ''.join(result_tokens)


def format_math_question(question_text: str) -> str:
    """Format a mathematical/chemistry question for display."""
    if not question_text:
        return ''
    
    return smart_wrap_math_segments(question_text)


def format_math_text(text: str) -> str:
    """Alias for format_math_question for use in serializers."""
    if not text:
        return ''
    
    return smart_wrap_math_segments(text)


def format_math_choices(choices: List[str]) -> List[str]:
    """Format an array of answer choices."""
    return [format_math_question(choice) for choice in choices]


def extract_math_expressions(text: str) -> List[str]:
    """Extract all mathematical expressions from text."""
    if not text:
        return []
    
    expressions = []
    inline_math = re.findall(r'\$([^$]+)\$', text)
    expressions.extend(inline_math)
    block_math = re.findall(r'\$\$([^$]+)\$\$', text)
    expressions.extend(block_math)
    return expressions


def is_valid_latex(latex: str) -> bool:
    """Validate LaTeX syntax (basic check for balanced braces)."""
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
    """Replace common symbol names with LaTeX equivalents."""
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
    """Format a batch of questions with math notation."""
    formatted_questions = []
    
    for question in questions:
        formatted_q = {
            **question,
            'text': format_math_question(question.get('text', '')),
        }
        
        if 'choices' in question:
            formatted_q['choices'] = format_math_choices(question['choices'])
        
        if 'options' in question:
            formatted_q['options'] = {
                key: format_math_question(value)
                for key, value in question['options'].items()
            }
        
        formatted_questions.append(formatted_q)
    
    return formatted_questions
