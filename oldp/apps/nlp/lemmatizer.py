from oldp.apps.nlp.base import SpacyNLP


def lemmatize(noun: str, lang='de'):
    nlp = SpacyNLP(lang=lang)
    container = nlp.process(noun)
    return next(container.lemmas())
