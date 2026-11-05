"""Receive mail from the legacy relay."""
import asyncore
import smtpd


class Inbox(smtpd.SMTPServer):
    def __init__(self, address, store):
        smtpd.SMTPServer.__init__(self, address, None)
        self.store = store

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        self.store.append((mailfrom, rcpttos, data))


def serve(address, store):
    Inbox(address, store)
    asyncore.loop()
