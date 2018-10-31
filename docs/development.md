# Development

This guide provides useful information for those who like to contribute to the project or just want into integrate it into their own.

## Useful links

- [Setting up a Django development environment by Mozilla](https://developer.mozilla.org/en-US/docs/Learn/Server-side/Django/development_environment)
- [PyCharm IDE with Django support](https://www.jetbrains.com/help/pycharm/django-support7.html)

## Write a custom processing step

A key part of OLDP is our data processing pipeline.
All the data stored on the platform can be used as starting point for further processing, e.g. information extraction.

We illustrate how this can be done with the example of *topic extraction*.
In our example we want to assign one or more topics to a law book.
Hereby, a topic means a tag, category or list that helps users finding relevant information.

We start with a new Django app in `oldp/apps/topics` and add it to the `settings.py`.
Next, we define simple models.
`Topic` represents a topic with a descriptive `title`.
`TopicContent` is an abstract class that we use as mixin to add the `topics` field to the `LawBook` model.

```python
# oldp/apps/topics/models.py

class Topic(db.models):
    title = models.CharField(
        max_length=200,
        help_text='Verbose title of topic',
        unique=True,
    )

class TopicContent(db.models):
    topics = models.ManyToManyField(
        Topic,
        help_text='Topics that are covered by this content',
        blank=True,
    )

    class Meta:
        abstract = True

```

Extent the target model (`LawBook` in our case) with TopicContent:

```python
# oldp/apps/laws/models.py

class LawBook(TopicContent): # BEFORE: class LawBook(db.models):
    # ...

# multiple inherits are possible:
# class Law(TopicContent, SearchContent, SomeOtherContent, ...):
```

Make and apply migrations:

```bash
./manage.py makemigrations
./manage.py migrate
```


For the actual processing step we need to implement as class called `ProcessingStep` that inherits from
`BaseProcessingStep` or the corresponding content class. Here, we inherit from `LawBookProcessingStep`.

The cornerstone of each processing step is the `process` method which takes as input a `LawBook`, does the processing
and then returns the processed `LawBook`.

In our example, we added an `__init__` that pre-loads all available topics. Then, the actual `process` only assigns
five random topics to the law book:

```python
# oldp/apps/topics/processing/processing_steps/assign_topics_to_law_book.py

class ProcessingStep(LawBookProcessingStep):
    description = 'Assign topics'

    def __init__(self):
        super().__init__()
        self.topics = Topic.objects.all()

    def process(self, law_book: LawBook) -> LawBook:
        # Remove existing topics
        law_book.topics.clean()

        # Select 5 random topics
        for t in random.sample(self.topics, 5):
            law_book.topics.add(t)

        law_book.save()

        return law_book
```

Add processing step to settings:

```python
# oldp/settings.py
# ...

# Processing pipeline
PROCESSING_STEPS = {
    # ...
    'LawBook': [
        'oldp.apps.topics.processing.processing_steps.assign_topics_to_law_book',  # Add this line
    ]
}

# ...
```

If the processing step is added to the settings and the corresponding admin class inherits from `ProcessingStepActionsAdmin`,
the processing step gets automatically available as admin action.
