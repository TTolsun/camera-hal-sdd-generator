"""Exact historical HTTP policy aliases; never extend eligibility implicitly."""

# Only the exact reviewed policy hash is HTTP-compatible with its predecessor:
# frozen-source tests compare HTTP requests and validation decisions/messages.
# Typed malformed-review errors change retry behavior, never accepted verdicts.
# CLI always keeps the current hash. Any later source edit misses this pair.
HTTP_GROUNDING_SCHEMA_COMPATIBILITY = {
    '3c9673abb403dee9aa554ee5b3c549ebfe95bb18ec0e9cd7bf6e495e060439c2':
        'c54006f7c90cb2af955e1ede18b761c7feb22dffa3bc37a885c019508348eba0',
}
HTTP_PROVIDERS = ('ollama', 'openai-compatible')


def http_grounding_policy(current):
    return HTTP_GROUNDING_SCHEMA_COMPATIBILITY.get(current, current)


def generation_policy(current, kind):
    return http_grounding_policy(current) if kind in HTTP_PROVIDERS else current


def allowed_policies(current, artifact):
    allowed = {current}
    origins, answers = artifact.get('topic_agents'), artifact.get('answers')
    # Missing, partial and mixed producer maps never establish HTTP origin.
    if (isinstance(answers, dict) and answers and isinstance(origins, dict)
            and set(origins) == set(answers)
            and all(isinstance(value, str) and value.partition('/')[0] in HTTP_PROVIDERS
                    and value.partition('/')[2] for value in origins.values())):
        allowed.add(http_grounding_policy(current))
    return allowed


