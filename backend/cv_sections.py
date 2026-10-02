"""Explicit CV heading aliases and evidence-preserving skill lists. No AI."""
import re
import unicodedata

ALIASES = {
    'PROFILE': ('profile', 'summary', 'professional summary', 'professional profile', 'career summary', 'objective'),
    'TECHNICAL SKILLS': ('technical skills', 'skills', 'key skills', 'core skills', 'professional skills', 'core competencies'),
    'EXPERIENCE': ('experience', 'work experience', 'professional experience', 'employment', 'employment history', 'internships'),
    'PERSONAL PROJECTS': ('personal projects', 'projects', 'academic projects', 'selected projects'),
    'EDUCATION': ('education', 'academic background', 'qualifications'),
    'CERTIFICATIONS AND COURSES': ('certifications and courses', 'certifications & courses', 'certifications', 'certificates', 'courses', 'training', 'certifications and training'),
}
BOUNDARIES = {'languages', 'interests', 'hobbies', 'references', 'publications',
              'awards', 'volunteering', 'volunteer experience', 'additional information'}


def heading_key(line):
    value = unicodedata.normalize('NFKC', line)
    return re.sub(r'\s+', ' ', value).strip().rstrip(':').strip().casefold()


def parse_sections(lines):
    lookup = {alias: section for section, aliases in ALIASES.items() for alias in aliases}
    sections, active = {}, None
    for line in lines:
        key = heading_key(line)
        if key in lookup:
            active = lookup[key]
            sections.setdefault(active, [])
        elif key in BOUNDARIES:
            active = None
        elif active:
            sections[active].append(line)
    return sections


def skill_facts(lines):
    seen, context = set(), ''
    for line in lines:
        value = re.sub(r'^[\s\u2022\u25cf\u25aa\ufffd*-]+', '', line).strip()
        if ':' in value:
            context, value = (part.strip() for part in value.split(':', 1))
        for part in re.split(r'[,;\u2022\u25cf\u25aa]', value):
            fact = part.strip()
            if fact and fact.casefold() not in seen:
                seen.add(fact.casefold())
                yield fact, context
