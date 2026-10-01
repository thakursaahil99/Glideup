"""Skill taxonomy: canonical names, aliases and categories.

Used to normalise LLM output (so "JS", "javascript" and "Javascript" are one skill) and by
the offline heuristic parser. Unknown skills are kept as-is: the taxonomy improves
matching, it never discards what a resume says. Phase 9 makes this admin-editable.
"""

import re
from dataclasses import dataclass

# canonical name -> (category, aliases)
_TAXONOMY: dict[str, tuple[str, tuple[str, ...]]] = {
    # languages
    "Python": ("language", ("py", "python3")),
    "JavaScript": ("language", ("js", "ecmascript", "es6")),
    "TypeScript": ("language", ("ts",)),
    "Java": ("language", ()),
    "C#": ("language", ("csharp", "c sharp")),
    "C++": ("language", ("cpp",)),
    "C": ("language", ()),
    "Go": ("language", ("golang",)),
    "Rust": ("language", ()),
    "Kotlin": ("language", ()),
    "Swift": ("language", ()),
    "PHP": ("language", ()),
    "Ruby": ("language", ()),
    "Scala": ("language", ()),
    "SQL": ("language", ()),
    "Bash": ("language", ("shell", "shell scripting")),
    "HTML": ("language", ("html5",)),
    "CSS": ("language", ("css3",)),
    "Dart": ("language", ()),
    "R": ("language", ()),
    # frameworks / libraries
    "React": ("framework", ("react.js", "reactjs")),
    "Next.js": ("framework", ("nextjs", "next")),
    "Angular": ("framework", ("angularjs", "angular.js")),
    "Vue.js": ("framework", ("vue", "vuejs")),
    "Svelte": ("framework", ()),
    "Node.js": ("framework", ("node", "nodejs")),
    "Express": ("framework", ("express.js", "expressjs")),
    "NestJS": ("framework", ("nest.js",)),
    "FastAPI": ("framework", ()),
    "Django": ("framework", ()),
    "Flask": ("framework", ()),
    "Spring Boot": ("framework", ("spring", "springboot")),
    ".NET": ("framework", ("dotnet", ".net core", "asp.net", "asp.net core")),
    "Ruby on Rails": ("framework", ("rails",)),
    "Laravel": ("framework", ()),
    "React Native": ("framework", ()),
    "Flutter": ("framework", ()),
    "Redux": ("framework", ()),
    "Tailwind CSS": ("framework", ("tailwind", "tailwindcss")),
    "GraphQL": ("framework", ()),
    "gRPC": ("framework", ()),
    "Pandas": ("framework", ()),
    "NumPy": ("framework", ()),
    "PyTorch": ("framework", ()),
    "TensorFlow": ("framework", ()),
    "scikit-learn": ("framework", ("sklearn",)),
    "LangChain": ("framework", ()),
    "Celery": ("framework", ()),
    "SQLAlchemy": ("framework", ()),
    "jQuery": ("framework", ()),
    # databases
    "PostgreSQL": ("database", ("postgres", "postgresql", "psql")),
    "MySQL": ("database", ()),
    "SQL Server": ("database", ("mssql", "microsoft sql server")),
    "Oracle": ("database", ("oracle db",)),
    "MongoDB": ("database", ("mongo",)),
    "Redis": ("database", ()),
    "Elasticsearch": ("database", ("elastic search", "opensearch")),
    "DynamoDB": ("database", ()),
    "Cassandra": ("database", ()),
    "SQLite": ("database", ()),
    "Cosmos DB": ("database", ("cosmosdb", "azure cosmos db")),
    "pgvector": ("database", ()),
    # cloud
    "Azure": ("cloud", ("microsoft azure",)),
    "AWS": ("cloud", ("amazon web services",)),
    "GCP": ("cloud", ("google cloud", "google cloud platform")),
    "Firebase": ("cloud", ()),
    "Vercel": ("cloud", ()),
    # devops
    "Docker": ("devops", ()),
    "Kubernetes": ("devops", ("k8s",)),
    "Terraform": ("devops", ()),
    "GitHub Actions": ("devops", ()),
    "Azure DevOps": ("devops", ()),
    "Jenkins": ("devops", ()),
    "CI/CD": ("devops", ("ci cd", "continuous integration")),
    "Linux": ("devops", ()),
    "Nginx": ("devops", ()),
    "Kafka": ("devops", ("apache kafka",)),
    "RabbitMQ": ("devops", ()),
    "Prometheus": ("devops", ()),
    "Grafana": ("devops", ()),
    "Helm": ("devops", ()),
    "Ansible": ("devops", ()),
    # tools
    "Git": ("tool", ()),
    "Jira": ("tool", ()),
    "Figma": ("tool", ()),
    "Postman": ("tool", ()),
    "Webpack": ("tool", ()),
    "Vite": ("tool", ()),
    "Jest": ("tool", ()),
    "Pytest": ("tool", ()),
    "Playwright": ("tool", ()),
    "Cypress": ("tool", ()),
    "Selenium": ("tool", ()),
    # practices
    "REST APIs": ("practice", ("rest", "restful", "rest api", "restful apis")),
    "Microservices": ("practice", ("microservice",)),
    "System Design": ("practice", ()),
    "Data Structures & Algorithms": ("practice", ("dsa", "data structures", "algorithms")),
    "Machine Learning": ("practice", ("ml",)),
    "Generative AI": ("practice", ("genai", "llm", "llms", "large language models")),
    "Unit Testing": ("practice", ("tdd", "test driven development")),
    "Agile": ("practice", ("scrum", "kanban")),
    "OAuth": ("practice", ("oauth2", "oauth 2.0", "openid connect", "oidc")),
    "Distributed Systems": ("practice", ()),
    "Performance Optimization": ("practice", ()),
    "Accessibility": ("practice", ("a11y", "wcag")),
    "Security": ("practice", ("application security", "owasp")),
    # soft skills
    "Leadership": ("soft", ("team leadership", "led a team", "mentoring", "mentorship")),
    "Communication": ("soft", ()),
    "Stakeholder Management": ("soft", ()),
}

CATEGORIES = (
    "language",
    "framework",
    "database",
    "cloud",
    "devops",
    "tool",
    "practice",
    "soft",
    "other",
)


@dataclass(frozen=True, slots=True)
class CanonicalSkill:
    name: str
    normalized: str
    category: str | None


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


_LOOKUP: dict[str, tuple[str, str]] = {}
for _name, (_category, _aliases) in _TAXONOMY.items():
    for _alias in (_name, *_aliases):
        _LOOKUP[_key(_alias)] = (_name, _category)


def canonicalize(raw: str) -> CanonicalSkill:
    """Map a raw skill string to its canonical form (unknown skills keep their spelling)."""
    cleaned = re.sub(r"\s+", " ", raw.strip())[:100]
    match = _LOOKUP.get(_key(cleaned))
    if match:
        name, category = match
        return CanonicalSkill(name=name, normalized=_key(name), category=category)
    return CanonicalSkill(name=cleaned, normalized=_key(cleaned), category=None)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    # Word-ish boundaries that also work for names like "C#", "C++", ".NET", "Node.js".
    return re.compile(rf"(?<![\w.+#]){re.escape(alias)}(?![\w+#])", re.IGNORECASE)


# Aliases too ambiguous to detect in free text (single letters, common words).
_NOT_DETECTABLE = {"c", "r", "go", "next", "node", "rest", "ml", "ts", "py", "spring", "express"}

_DETECTORS: list[tuple[str, str, re.Pattern[str]]] = [
    (name, category, _alias_pattern(alias))
    for name, (category, aliases) in _TAXONOMY.items()
    for alias in (name, *aliases)
    if _key(alias) not in _NOT_DETECTABLE
]


def detect_skills(text: str) -> list[tuple[str, str]]:
    """Find known skills mentioned in free text: [(canonical name, category)]."""
    found: dict[str, str] = {}
    for name, category, pattern in _DETECTORS:
        if name not in found and pattern.search(text):
            found[name] = category
    return sorted(found.items())
