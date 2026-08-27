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

# Pattern to detect chemical formula-like strings: at least one uppercase letter
# followed by lowercase and/or digits, with subscripts
CHEMICAL_FORMULA_PATTERN = re.compile(
    r'\b([A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?(?:\d+)?)*(?:\([A-Z][a-z]?(?:\d+)?\)\d*)*)\b'
)

# Pattern to detect if a string looks like a chemical formula
# Must have: uppercase letter + (lowercase letter or digit) and contain at least one digit
CHEMICAL_LIKE_PATTERN = re.compile(
    r'^[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*(?:\([A-Z][a-z]?\d*\)\d*)*$'
)


def is_chemical_formula(text: str) -> bool:
    """
    Check if a string looks like a chemical formula.
    
    Examples that match: H2O, NaCl, H2SO4, Ca(OH)2, C6H12O6, O2, Fe2O3
    Examples that don't match: Hello, World, ISBN, PDF, ABC
    """
    text = text.strip()
    if not text or len(text) < 2:
        return False
    
    # Check against known formulas first
    if text in CHEMICAL_FORMULAS:
        return True
    
    # Heuristic: must match chemical pattern AND contain at least one digit
    # (to distinguish from regular words/abbreviations like "DNA", "RNA", "ATP")
    if CHEMICAL_LIKE_PATTERN.match(text) and re.search(r'\d', text):
        return True
    
    return False


def format_chemical_formula(formula: str) -> str:
    """
    Convert a chemical formula to LaTeX using \\ce{} (mhchem) notation.
    
    Examples:
        H2O -> \\ce{H2O}
        H2SO4 -> \\ce{H2SO4}
        Ca(OH)2 -> \\ce{Ca(OH)2}
    """
    return '$\\ce{' + str(formula) + '}$'


def convert_reaction_arrows(text: str) -> str:
    """
    Convert common reaction arrow notations to LaTeX.
    
    Examples:
        -> or --> or → -> \\rightarrow
        <-> or <=> or ⇌ -> \\rightleftharpoons
    """
    # Reversible reaction arrows (must check before single arrows)
    text = re.sub(r'\s*<\s*=\s*>\s*', r' $\\rightleftharpoons$ ', text)
    text = re.sub(r'\s*<\s*-\s*>\s*', r' $\\rightleftharpoons$ ', text)
    text = re.sub(r'\s*⇌\s*', r' $\\rightleftharpoons$ ', text)
    
    # Forward reaction arrows
    text = re.sub(r'\s*-\s*-\s*>\s*', r' $\\rightarrow$ ', text)
    text = re.sub(r'\s*-\s*>\s*', r' $\\rightarrow$ ', text)
    text = re.sub(r'\s*→\s*', r' $\\rightarrow$ ', text)
    
    return text


def convert_scientific_notation(text: str) -> str:
    """
    Convert scientific notation patterns to LaTeX.
    
    Examples:
        6.02 x 10^23 -> $6.02 \\times 10^{23}$
        3.0 × 10^8 -> $3.0 \\times 10^{8}$
        1.6e-19 -> $1.6 \\times 10^{-19}$
    """
    # Pattern: number x 10^number or number × 10^number
    text = re.sub(
        r'(\d+\.?\d*)\s*[x×\*]\s*10\s*\^\s*\{?\s*(-?\d+)\s*\}?',
        r'$\1 \\times 10^{\2}$',
        text
    )
    
    # Pattern: number e/E ±number (e.g., 1.6e-19)
    text = re.sub(
        r'(\d+\.?\d*)\s*[eE]\s*(-?\d+)',
        r'$\1 \\times 10^{\2}$',
        text
    )
    
    return text


def convert_ionic_charges(text: str) -> str:
    """
    Convert ionic charge notation to LaTeX.
    
    Examples:
        Ca^2+ -> $\\text{Ca}^{2+}$
        SO4^2- -> $\\text{SO}_4^{2-}$
        Fe^3+ -> $\\text{Fe}^{3+}$
    """
    # Pattern: Element^charge (e.g., Ca^2+, Fe^3+, Cl^-)
    text = re.sub(
        r'\b([A-Z][a-z]?(?:\d*))\s*\^\s*(\d*[+-])',
        lambda m: '$\\text{' + m.group(1) + '}^{' + m.group(2) + '}$',
        text
    )
    
    return text


def convert_to_latex(text: str) -> str:
    """
    Convert simple math notation to LaTeX format.
    Only converts the math syntax markers, does NOT wrap in delimiters.
    
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
    
    # Convert fractions: 1/2 -> \frac{1}{2} (only numeric fractions)
    result = re.sub(r'(\d+)/(\d+)', r'\\frac{\1}{\2}', result)
    
    # Convert subscripts: x_1 -> x_{1}, x_n -> x_{n}
    result = re.sub(r'_(\d+)', r'_{\1}', result)
    result = re.sub(r'_([a-zA-Z])', r'_{\1}', result)
    
    return result


def has_math_notation(text: str) -> bool:
    """
    Check if a SEGMENT of text contains mathematical notation.
    More conservative than before — checks for actual math constructs,
    not just any occurrence of ^ or _.
    
    Args:
        text: The text segment to check
        
    Returns:
        True if text contains clear math patterns
    """
    if not text:
        return False
    
    math_patterns = [
        r'\^{',             # Already-converted LaTeX power
        r'_{',              # Already-converted LaTeX subscript
        r'\\sqrt',          # LaTeX sqrt
        r'\\frac',          # LaTeX fraction
        r'\w\^\d',          # Power notation: x^2
        r'\w\^[a-zA-Z]',   # Power notation: x^n
        r'\w_\d',           # Subscript: x_1
        r'sqrt\(',          # sqrt function
        r'\d+/\d+',         # Numeric fraction
        r'\\[a-z]+{',       # LaTeX command with argument
    ]
    
    return any(re.search(pattern, text) for pattern in math_patterns)


def smart_wrap_math_segments(text: str) -> str:
    """
    Intelligently wrap only math segments in LaTeX delimiters.
    
    Instead of wrapping the entire string (which destroys readability of
    English text in math mode), this function:
    1. Tokenizes the text into words/segments
    2. Identifies which segments contain math notation
    3. Wraps only those segments in $...$
    4. Auto-detects and converts chemical formulas using \\ce{}
    5. Leaves plain English text untouched
    
    This is backward-compatible with existing questions that already have
    $ delimiters — those pass through unchanged.
    """
    if not text:
        return ''
    
    # If text already has $ delimiters, it's already formatted — pass through
    if '$' in text:
        return text
    
    # Step 1: Handle reaction arrows (before tokenizing)
    text = convert_reaction_arrows(text)
    
    # If reaction arrow conversion already added $ delimiters, return
    if '$' in text:
        # Also handle scientific notation and ionic charges in remaining text
        text = convert_scientific_notation(text)
        text = convert_ionic_charges(text)
        return text
    
    # Step 2: Handle scientific notation (e.g., 6.02 x 10^23)
    text = convert_scientific_notation(text)
    if '$' in text:
        text = convert_ionic_charges(text)
        return _process_remaining_math(text)
    
    # Step 3: Handle ionic charges (e.g., Ca^2+)
    text = convert_ionic_charges(text)
    if '$' in text:
        return _process_remaining_math(text)
    
    # Step 4: Tokenize and process word by word
    return _process_remaining_math(text)


def _process_remaining_math(text: str) -> str:
    """
    Process text that may have some $ delimiters already added
    and some plain math segments remaining.
    """
    # Split on existing $ delimiters to avoid re-processing them
    parts = re.split(r'(\$[^$]+\$|\$\$[^$]+\$\$)', text)
    result_parts = []
    
    for part in parts:
        if not part:
            continue
        # If this part is already wrapped in $, pass through
        if part.startswith('$'):
            result_parts.append(part)
            continue
        # Process this segment for math and chemistry
        result_parts.append(_wrap_segment_math(part))
    
    return ''.join(result_parts)


def _wrap_segment_math(text: str) -> str:
    """
    Process a text segment (without existing $ delimiters) to wrap
    math expressions and chemical formulas.
    """
    # Split into tokens (words and whitespace)
    tokens = re.split(r'(\s+)', text)
    result_tokens = []
    
    for token in tokens:
        if not token or token.isspace():
            result_tokens.append(token)
            continue
        
        # Strip punctuation for checking, but preserve it in output
        stripped = token.strip('.,;:!?()[]{}')
        leading = token[:len(token) - len(token.lstrip('.,;:!?()[]{}'))]
        trailing = token[len(stripped) + len(leading):]
        
        # Check if it's a known chemical formula
        if is_chemical_formula(stripped):
            result_tokens.append(leading + '$\\ce{' + stripped + '}$' + trailing)
        # Check if it contains math notation
        elif has_math_notation(stripped):
            converted = convert_to_latex(stripped)
            result_tokens.append(leading + '$' + converted + '$' + trailing)
        else:
            result_tokens.append(token)
    
    return ''.join(result_tokens)


def format_math_question(question_text: str) -> str:
    """
    Format a mathematical/chemistry question for display.
    
    FIXED: No longer wraps the entire sentence in $ delimiters.
    Instead, only wraps individual math/chemistry segments.
    
    Backward-compatible: questions that already have $ delimiters
    pass through unchanged.
    
    Args:
        question_text: The question text
        
    Returns:
        Formatted question text ready for KaTeX rendering
    """
    if not question_text:
        return ''
    
    return smart_wrap_math_segments(question_text)


def format_math_text(text: str) -> str:
    """
    Alias for format_math_question for use in serializers.
    Formats text that may contain math or chemistry notation.
    
    Args:
        text: The text to format
        
    Returns:
        Formatted text ready for KaTeX rendering
    """
    if not text:
        return ''
    
    return smart_wrap_math_segments(text)


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
