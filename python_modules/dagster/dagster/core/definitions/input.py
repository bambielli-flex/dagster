from collections import namedtuple
from dagster import check

from dagster.core.types.runtime import RuntimeType, resolve_to_runtime_type

from .expectation import ExpectationDefinition
from .utils import check_valid_name


class InputDefinition(object):
    '''An InputDefinition instance represents an argument to a compute defined within a solid.
    Inputs are values within the dagster type system that are created from previous solids.

    Attributes:
        name (str): Name of the input.
        runtime_type (DagsterType): Type of the input. Defaults to types.Any
        expectations (List[ExpectationDefinition]):
            List of expectations that applies to the value passed to the solid.
        description (str): Description of the input. Optional.
    '''

    def __init__(self, name, dagster_type=None, expectations=None, description=None):
        ''
        self.name = check_valid_name(name)

        self.runtime_type = check.inst(resolve_to_runtime_type(dagster_type), RuntimeType)

        self.expectations = check.opt_list_param(
            expectations, 'expectations', of_type=ExpectationDefinition
        )
        self.description = check.opt_str_param(description, 'description')

    @property
    def descriptive_key(self):
        return 'output'

    def mapping_to(self, solid_name, input_name):
        return InputMapping(self, solid_name, input_name)


class InputMapping(namedtuple('_InputMapping', 'definition solid_name input_name')):
    def __new__(cls, definition, solid_name, input_name):
        return super(InputMapping, cls).__new__(
            cls,
            check.inst_param(definition, 'definition', InputDefinition),
            check.str_param(solid_name, 'solid_name'),
            check.str_param(input_name, 'input_name'),
        )
