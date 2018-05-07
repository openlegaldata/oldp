import logging
from enum import Enum

from oldp.apps.backend.processing.processing_steps.post import PostProcessingStep

logger = logging.getLogger(__name__)

PostProcessingAction = Enum('PostProcessingAction', 'KEEP MOVE REMOVE')


class SendToFS(PostProcessingStep):
    def process(self, content):
        raise NotImplementedError('SendToFS is not implemented yet')
