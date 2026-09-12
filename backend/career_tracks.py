"""Local, inspectable career tracks used for CV suggestions, matching and searches."""
from collections import OrderedDict
import re

VERSION = 'career-tracks-1'

TRACKS = OrderedDict({
    'CYBERSECURITY': {
        'label': 'Cybersecurity',
        'description': 'SOC, information security, GRC, identity, vulnerability and defensive security roles.',
        'families': {
            'SOC / Detection': ['soc', 'security operations', 'security monitoring', 'siem', 'blue team', 'cyber defence', 'cyber defense', 'secops', 'detection engineering'],
            'Threat / Incident Response': ['threat intelligence', 'threat analyst', 'threat hunting', 'incident response', 'dfir', 'digital forensics'],
            'Information / IT Security': ['cybersecurity', 'cyber security', 'information security', 'it security', 'security analyst', 'security engineer', 'security consultant', 'security specialist', 'أمن المعلومات', 'أمن سيبراني'],
            'Network / Cloud Security': ['network security', 'cloud security', 'endpoint security', 'application security', 'devsecops'],
            'Identity / Access': ['iam', 'pam', 'identity and access', 'identity access', 'privileged access'],
            'Vulnerability': ['vulnerability', 'penetration test', 'pentest'],
            'GRC / Technology Risk': ['grc', 'it risk', 'technology risk', 'it audit', 'it compliance', 'security compliance', 'information security governance'],
        },
        'target_roles': ['SOC Analyst', 'Cybersecurity Analyst', 'Security Analyst', 'Information Security Analyst', 'Graduate Security Analyst', 'IT Security Analyst', 'GRC Analyst', 'Network Security Analyst', 'Junior Incident Response Analyst'],
        'adjacent_roles': ['IT Support', 'Systems Administrator', 'Network Operations', 'Cloud Operations'],
        'skills': ['SIEM', 'SOC', 'log analysis', 'security monitoring', 'Nmap', 'Metasploit', 'TCP/IP', 'DNS', 'Linux', 'Python', 'ISO 27001', 'risk assessment', 'vulnerability assessment', 'Microsoft Sentinel', 'Splunk', 'CrowdStrike', 'QRadar', 'KQL', 'IAM', 'incident response', 'network security', 'cloud security', 'Security+', 'CCNA'],
        'resume_signals': ['cybersecurity', 'cyber security', 'information security', 'soc', 'siem', 'nmap', 'metasploit', 'vulnerability', 'incident response', 'network security', 'iso 27001', 'splunk', 'sentinel'],
        'queries': ['SOC Analyst', 'Cybersecurity Analyst', 'Information Security Analyst', 'GRC Analyst', 'IT Security Analyst'],
        'credentials': ['CISSP', 'OSCP', 'CCNA', 'Security+', 'SC-200'],
        'core_skills': ['soc', 'siem', 'linux', 'python', 'incident response', 'network security', 'risk assessment', 'vulnerability', 'iam', 'cloud security', 'splunk', 'security monitoring'],
    },
    'DATA_ANALYTICS': {
        'label': 'Data & Analytics',
        'description': 'Data analyst, business intelligence and reporting roles.',
        'families': {
            'Data Analysis': ['data analyst', 'data analytics', 'analytics analyst', 'reporting analyst', 'insights analyst'],
            'Business Intelligence': ['business intelligence', 'bi analyst', 'power bi analyst', 'tableau analyst'],
            'Business / Product Analysis': ['business analyst', 'product analyst', 'operations analyst', 'marketing analyst'],
        },
        'target_roles': ['Graduate Data Analyst', 'Junior Data Analyst', 'Data Analyst', 'Business Intelligence Analyst', 'Reporting Analyst', 'Business Analyst'],
        'adjacent_roles': ['Operations Analyst', 'MIS Analyst', 'Data Coordinator'],
        'skills': ['SQL', 'Python', 'Excel', 'Power BI', 'Tableau', 'pandas', 'NumPy', 'statistics', 'data visualization', 'data cleaning', 'ETL', 'dashboard', 'scikit-learn'],
        'resume_signals': ['data analysis', 'data analytics', 'sql', 'power bi', 'tableau', 'pandas', 'numpy', 'statistics', 'data visualization', 'dashboard', 'excel'],
        'queries': ['Graduate Data Analyst', 'Junior Data Analyst', 'Business Intelligence Analyst', 'Reporting Analyst', 'Business Analyst'],
        'credentials': ['Google Data Analytics', 'Microsoft Power BI Data Analyst', 'Tableau Desktop Specialist'],
        'core_skills': ['sql', 'power bi', 'tableau', 'excel', 'pandas', 'statistics', 'data visualization', 'dashboard'],
    },
    'SOFTWARE_ENGINEERING': {
        'label': 'Software Engineering',
        'description': 'Graduate and junior software, web, mobile and backend roles.',
        'families': {
            'Software Engineering': ['software engineer', 'software developer', 'application developer', 'programmer'],
            'Web Engineering': ['frontend developer', 'front end developer', 'backend developer', 'back end developer', 'full stack developer', 'fullstack developer', 'web developer'],
            'Mobile Engineering': ['mobile developer', 'android developer', 'ios developer', 'flutter developer'],
        },
        'target_roles': ['Graduate Software Engineer', 'Junior Software Engineer', 'Software Developer', 'Backend Developer', 'Frontend Developer', 'Full Stack Developer'],
        'adjacent_roles': ['Application Support Analyst', 'Technical Consultant', 'Implementation Engineer'],
        'skills': ['Python', 'Java', 'JavaScript', 'TypeScript', 'React', 'Node.js', 'C#', '.NET', 'Git', 'REST API', 'HTML', 'CSS', 'SQL', 'Docker', 'Spring', 'Django', 'FastAPI'],
        'resume_signals': ['software engineering', 'software development', 'java', 'javascript', 'typescript', 'react', 'node.js', 'c#', '.net', 'rest api', 'frontend', 'backend', 'full stack', 'git'],
        'queries': ['Graduate Software Engineer', 'Junior Software Developer', 'Junior Backend Developer', 'Junior Frontend Developer', 'Graduate Technology Developer'],
        'credentials': [],
        'core_skills': ['python', 'java', 'javascript', 'typescript', 'react', 'node.js', 'git', 'rest api', 'sql'],
    },
    'AI_ML': {
        'label': 'AI & Machine Learning',
        'description': 'Entry-level machine learning, AI and applied data science roles.',
        'families': {
            'Machine Learning': ['machine learning engineer', 'ml engineer', 'machine learning analyst'],
            'Artificial Intelligence': ['ai engineer', 'artificial intelligence engineer', 'generative ai engineer'],
            'Data Science': ['data scientist', 'junior data scientist', 'applied scientist'],
        },
        'target_roles': ['Graduate Machine Learning Engineer', 'Junior AI Engineer', 'Junior Data Scientist', 'Machine Learning Analyst'],
        'adjacent_roles': ['Data Analyst', 'Python Developer', 'AI Research Assistant'],
        'skills': ['Python', 'scikit-learn', 'TensorFlow', 'PyTorch', 'pandas', 'NumPy', 'machine learning', 'deep learning', 'NLP', 'computer vision', 'statistics', 'Jupyter'],
        'resume_signals': ['machine learning', 'artificial intelligence', 'data science', 'scikit-learn', 'tensorflow', 'pytorch', 'deep learning', 'nlp', 'computer vision', 'jupyter'],
        'queries': ['Graduate Machine Learning Engineer', 'Junior AI Engineer', 'Junior Data Scientist', 'AI Research Assistant'],
        'credentials': ['TensorFlow Developer Certificate'],
        'core_skills': ['python', 'scikit-learn', 'tensorflow', 'pytorch', 'machine learning', 'deep learning', 'nlp', 'statistics'],
    },
    'IT_CLOUD': {
        'label': 'IT, Cloud & Networks',
        'description': 'IT support, systems, cloud, infrastructure and networking roles.',
        'families': {
            'IT Support': ['it support', 'technical support', 'service desk', 'help desk', 'helpdesk', 'desktop support'],
            'Systems / Cloud': ['systems administrator', 'system administrator', 'cloud engineer', 'cloud support', 'infrastructure engineer'],
            'Networking': ['network engineer', 'network administrator', 'network operations', 'noc analyst', 'noc engineer'],
        },
        'target_roles': ['Graduate IT Support Analyst', 'Junior Systems Administrator', 'Cloud Support Associate', 'Junior Network Engineer', 'NOC Analyst'],
        'adjacent_roles': ['Technical Support Engineer', 'Application Support Analyst', 'IT Operations Analyst'],
        'skills': ['Windows', 'Linux', 'Active Directory', 'Azure', 'AWS', 'TCP/IP', 'DNS', 'DHCP', 'Microsoft 365', 'PowerShell', 'Bash', 'CCNA', 'virtualization'],
        'resume_signals': ['it support', 'technical support', 'active directory', 'azure', 'aws', 'tcp/ip', 'dns', 'dhcp', 'microsoft 365', 'powershell', 'ccna', 'networking'],
        'queries': ['Graduate IT Support Analyst', 'Cloud Support Associate', 'Junior Network Engineer', 'NOC Analyst', 'Junior Systems Administrator'],
        'credentials': ['CCNA', 'AZ-900', 'AWS Cloud Practitioner', 'CompTIA A+'],
        'core_skills': ['windows', 'linux', 'active directory', 'azure', 'aws', 'tcp/ip', 'dns', 'powershell'],
    },
    'QA_TESTING': {
        'label': 'QA & Software Testing',
        'description': 'Manual and automated software testing and quality assurance roles.',
        'families': {
            'Quality Assurance': ['qa analyst', 'quality assurance analyst', 'quality assurance engineer', 'software tester'],
            'Test Engineering': ['test engineer', 'automation test engineer', 'test automation engineer', 'qa engineer'],
        },
        'target_roles': ['Graduate QA Analyst', 'Junior QA Engineer', 'Software Tester', 'Junior Test Engineer'],
        'adjacent_roles': ['Application Support Analyst', 'Product Support Analyst', 'UAT Analyst'],
        'skills': ['manual testing', 'test cases', 'Selenium', 'Cypress', 'Playwright', 'Postman', 'API testing', 'Jira', 'SQL', 'Python', 'Java', 'test automation'],
        'resume_signals': ['quality assurance', 'software testing', 'manual testing', 'test cases', 'selenium', 'cypress', 'playwright', 'postman', 'api testing', 'test automation'],
        'queries': ['Graduate QA Analyst', 'Junior QA Engineer', 'Software Tester', 'Junior Test Engineer'],
        'credentials': ['ISTQB'],
        'core_skills': ['manual testing', 'test cases', 'selenium', 'cypress', 'postman', 'api testing', 'sql', 'jira'],
    },
})

def _has(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text or '', re.I))

def selected_ids(cfg):
    return [key for key in (cfg or {}).get('career_tracks', []) if key in TRACKS]

def active_tracks(cfg):
    ids = selected_ids(cfg)
    return [TRACKS[key] for key in ids] if ids else list(TRACKS.values())

def families(cfg):
    output = OrderedDict()
    for track in active_tracks(cfg): output.update(track['families'])
    return output

def adjacent_roles(cfg):
    return list(dict.fromkeys(role.casefold() for track in active_tracks(cfg) for role in track['adjacent_roles']))

def matching_skills(cfg):
    return list(dict.fromkeys(skill for track in active_tracks(cfg) for skill in track['skills']))

def core_skills(cfg):
    return list(dict.fromkeys(skill.casefold() for track in active_tracks(cfg) for skill in track.get('core_skills', [])))

def credentials(cfg):
    return list(dict.fromkeys(cred for track in active_tracks(cfg) for cred in track.get('credentials', [])))

def search_queries(cfg):
    custom = [x.strip() for x in (cfg or {}).get('custom_target_roles', []) if x.strip()]
    generated = [q for track in active_tracks(cfg) for q in track['queries']]
    return list(dict.fromkeys(custom + generated))[:30]

def suggest(text):
    text = text or ''
    suggestions = []
    for key, track in TRACKS.items():
        evidence = [signal for signal in track['resume_signals'] if _has(text, signal)]
        skill_evidence = [skill for skill in track['skills'] if _has(text, skill)]
        evidence = list(dict.fromkeys(evidence + skill_evidence))[:8]
        suggestions.append({'id': key, 'label': track['label'], 'description': track['description'], 'signal_count': len(evidence), 'evidence': evidence})
    return sorted(suggestions, key=lambda row: (-row['signal_count'], list(TRACKS).index(row['id'])))

def public_tracks():
    return [{'id': key, 'label': value['label'], 'description': value['description'], 'target_roles': value['target_roles']} for key, value in TRACKS.items()]
