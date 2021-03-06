import pytest

from dagster import (
    CompositeSolidDefinition,
    DependencyDefinition,
    PipelineDefinition,
    SolidInstance,
    execute_pipeline,
    Field,
    String,
    solid,
    InputDefinition,
    OutputDefinition,
    ExpectationDefinition,
    ExpectationResult,
    DagsterInvalidDefinitionError,
)
from dagster.core.utility_solids import (
    create_root_solid,
    create_solid_with_deps,
    define_stub_solid,
    input_set,
)


def test_composite_basic_execution():
    a_source = define_stub_solid('A_source', [input_set('A_input')])
    node_a = create_root_solid('A')
    node_b = create_solid_with_deps('B', node_a)
    node_c = create_solid_with_deps('C', node_a)
    node_d = create_solid_with_deps('D', node_b, node_c)

    diamond_composite = CompositeSolidDefinition(
        name='diamond_composite',
        solids=[a_source, node_a, node_b, node_c, node_d],
        dependencies={
            'A': {'A_input': DependencyDefinition('A_source')},
            'B': {'A': DependencyDefinition('A')},
            'C': {'A': DependencyDefinition('A')},
            'D': {'B': DependencyDefinition('B'), 'C': DependencyDefinition('C')},
        },
    )

    result = execute_pipeline(PipelineDefinition(solids=[diamond_composite]))
    assert result.success

    result = execute_pipeline(
        PipelineDefinition(
            solids=[diamond_composite],
            dependencies={
                SolidInstance('diamond_composite', alias='D1'): {},
                SolidInstance('diamond_composite', alias='D2'): {},
            },
        )
    )
    assert result.success

    wrapped_composite = CompositeSolidDefinition(
        name='wrapped_composite', solids=[diamond_composite]
    )
    result = execute_pipeline(PipelineDefinition(solids=[diamond_composite, wrapped_composite]))
    assert result.success

    empty_composite = CompositeSolidDefinition(name='empty', solids=[])
    result = execute_pipeline(PipelineDefinition(solids=[empty_composite]))
    assert result.success


def test_composite_config():
    called = {}

    @solid(config_field=Field(String))
    def configured(context):
        called['configured'] = True
        assert context.solid_config is 'yes'

    inner = CompositeSolidDefinition(name='inner', solids=[configured])
    outer = CompositeSolidDefinition(name='outer', solids=[inner])
    pipeline = PipelineDefinition(name='composites_pipeline', solids=[outer])
    result = execute_pipeline(
        pipeline,
        {'solids': {'outer': {'solids': {'inner': {'solids': {'configured': {'config': 'yes'}}}}}}},
    )
    assert result.success
    assert called['configured']


def test_composite_config_input():
    called = {}

    @solid(inputs=[InputDefinition('one')])
    def node_a(_context, one):
        called['node_a'] = True
        assert one is 1

    inner = CompositeSolidDefinition(name='inner', solids=[node_a])
    outer = CompositeSolidDefinition(name='outer', solids=[inner])
    pipeline = PipelineDefinition(name='composites_pipeline', solids=[outer])
    result = execute_pipeline(
        pipeline,
        {
            'solids': {
                'outer': {
                    'solids': {'inner': {'solids': {'node_a': {'inputs': {'one': {'value': 1}}}}}}
                }
            }
        },
    )
    assert result.success
    assert called['node_a']


def test_mapped_composite_config_input():
    called = {}

    @solid(inputs=[InputDefinition('one')])
    def node_a(_context, one):
        called['node_a'] = True
        assert one is 1

    inner = CompositeSolidDefinition(
        name='inner',
        solids=[node_a],
        input_mappings=[InputDefinition('inner_one').mapping_to('node_a', 'one')],
    )
    outer = CompositeSolidDefinition(
        name='outer',
        solids=[inner],
        input_mappings=[InputDefinition('outer_one').mapping_to('inner', 'inner_one')],
    )
    pipeline = PipelineDefinition(name='composites_pipeline', solids=[outer])

    result = execute_pipeline(
        pipeline, {'solids': {'outer': {'inputs': {'outer_one': {'value': 1}}}}}
    )
    assert result.success
    assert called['node_a']


def test_mapped_composite_input_expectations():
    called = {}

    def exp_a(_c, _v):
        called['exp_a'] = True
        return ExpectationResult(True)

    @solid(inputs=[InputDefinition('one', expectations=[ExpectationDefinition('exp_a', exp_a)])])
    def node_a(_context, one):
        called['node_a'] = True
        assert one is 1

    def inner_exp(_c, _v):
        called['inner_exp'] = True
        return ExpectationResult(True)

    def outer_exp(_c, _v):
        called['outer_exp'] = True
        return ExpectationResult(True)

    inner = CompositeSolidDefinition(
        name='inner',
        solids=[node_a],
        input_mappings=[
            InputDefinition(
                name='inner_one', expectations=[ExpectationDefinition('inner_exp', inner_exp)]
            ).mapping_to('node_a', 'one')
        ],
    )
    outer = CompositeSolidDefinition(
        name='outer',
        solids=[inner],
        input_mappings=[
            InputDefinition(
                'outer_one', expectations=[ExpectationDefinition('outer_exp', outer_exp)]
            ).mapping_to('inner', 'inner_one')
        ],
    )
    pipeline = PipelineDefinition(name='composites_pipeline', solids=[outer])

    result = execute_pipeline(
        pipeline, {'solids': {'outer': {'inputs': {'outer_one': {'value': 1}}}}}
    )
    assert result.success
    assert called['node_a']
    assert called['exp_a']
    assert called['inner_exp']
    assert called['outer_exp']


def test_composite_io_mapping():
    a_source = define_stub_solid('A_source', [input_set('A_input')])
    node_a = create_root_solid('A')

    node_b = create_solid_with_deps('B', node_a)
    node_c = create_solid_with_deps('C', node_b)

    comp_a_inner = CompositeSolidDefinition(
        name='comp_a_inner',
        solids=[a_source, node_a],
        dependencies={'A': {'A_input': DependencyDefinition('A_source')}},
        output_mappings=[OutputDefinition().mapping_from('A')],
    )

    comp_a_outer = CompositeSolidDefinition(
        name='comp_a_outer',
        solids=[comp_a_inner],
        output_mappings=[OutputDefinition().mapping_from('comp_a_inner')],
    )

    comp_bc_inner = CompositeSolidDefinition(
        name='comp_bc_inner',
        solids=[node_b, node_c],
        dependencies={'C': {'B': DependencyDefinition('B')}},
        input_mappings=[
            InputDefinition(name='inner_B_in').mapping_to(solid_name='B', input_name='A')
        ],
    )

    comp_bc_outer = CompositeSolidDefinition(
        name='comp_bc_outer',
        solids=[comp_bc_inner],
        dependencies={},
        input_mappings=[
            InputDefinition(name='outer_B_in').mapping_to(
                solid_name='comp_bc_inner', input_name='inner_B_in'
            )
        ],
    )
    result = execute_pipeline(
        PipelineDefinition(
            name='wrapped_io',
            solids=[comp_a_outer, comp_bc_outer],
            dependencies={'comp_bc_outer': {'outer_B_in': DependencyDefinition('comp_a_outer')}},
        )
    )
    assert result.success


def test_io_error_is_decent():
    with pytest.raises(DagsterInvalidDefinitionError, match='mapping_to'):
        CompositeSolidDefinition(
            name='comp_a_outer', solids=[], input_mappings=[InputDefinition('should_be_mapped')]
        )

    with pytest.raises(DagsterInvalidDefinitionError, match='mapping_from'):
        CompositeSolidDefinition(
            name='comp_a_outer', solids=[], output_mappings=[OutputDefinition()]
        )
