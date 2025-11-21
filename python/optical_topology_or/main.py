import ncs
from ncs.application import Application
from .ot_actions import DiscoverTopology, BuildConnection, DeleteConnection

class Main(Application):
    def setup(self):
        self.log.info("Optical Topology OR: starting")

        self.register_action('discover-topology-ap', DiscoverTopology)
        self.register_action('build-connection-ap', BuildConnection)
        self.register_action('delete-connection-ap', DeleteConnection)

        self.log.info("Optical Topology OR: actions registered")

    def teardown(self):
        self.log.info("Optical Topology OR: stopping")


