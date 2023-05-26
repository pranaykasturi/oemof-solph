# -*- coding: utf-8 -*-

"""
In-development component to add some intelligence
to connection between two Nodes.

SPDX-FileCopyrightText: Uwe Krien <krien@uni-bremen.de>
SPDX-FileCopyrightText: Simon Hilpert
SPDX-FileCopyrightText: Cord Kaldemeyer
SPDX-FileCopyrightText: Patrik Schönfeldt
SPDX-FileCopyrightText: Johannes Röder
SPDX-FileCopyrightText: jakob-wo
SPDX-FileCopyrightText: gplssm
SPDX-FileCopyrightText: jnnr
SPDX-FileCopyrightText: Johannes Kochems

SPDX-License-Identifier: MIT

"""
from warnings import warn

from oemof.network import network as on
from oemof.tools import debugging
from pyomo.core import Set
from pyomo.core.base.block import ScalarBlock
from pyomo.environ import BuildAction
from pyomo.environ import Constraint

from oemof.solph._plumbing import sequence


class Link(on.Transformer):
    """A Link object with 2 inputs and 2 outputs.

    Parameters
    ----------
    conversion_factors : dict
        Dictionary containing conversion factors for conversion of each flow.
        Keys are the connected tuples (input, output) bus objects.
        The dictionary values can either be a scalar or an iterable with length
        of time horizon for simulation.

    Note: This component is experimental. Use it with care.

    Notes
    -----
    The sets, variables, constraints and objective parts are created
     * :py:class:`~oemof.solph.components.experimental._link.LinkBlock`

    Examples
    --------

    >>> from oemof import solph
    >>> bel0 = solph.buses.Bus(label="el0")
    >>> bel1 = solph.buses.Bus(label="el1")

    >>> link = solph.components.experimental.Link(
    ...    label="transshipment_link",
    ...    inputs={bel0: solph.flows.Flow(nominal_value=4),
    ...            bel1: solph.flows.Flow(nominal_value=2)},
    ...    outputs={bel0: solph.flows.Flow(),
    ...             bel1: solph.flows.Flow()},
    ...    conversion_factors={(bel0, bel1): 0.8, (bel1, bel0): 0.9})
    >>> print(sorted([x[1][5] for x in link.conversion_factors.items()]))
    [0.8, 0.9]

    >>> type(link)
    <class 'oemof.solph.components.experimental._link.Link'>

    >>> sorted([str(i) for i in link.inputs])
    ['el0', 'el1']

    >>> link.conversion_factors[(bel0, bel1)][3]
    0.8
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.conversion_factors = {
            k: sequence(v)
            for k, v in kwargs.get("conversion_factors", {}).items()
        }

        msg = (
            "Component `Link` should have exactly "
            + "2 inputs, 2 outputs, and 2 "
            + "conversion factors connecting these. You are initializing "
            + "a `Link`without obeying this specification. "
            + "If this is intended and you know what you are doing you can "
            + "disable the SuspiciousUsageWarning globally."
        )

        if (
            len(self.inputs) != 2
            or len(self.outputs) != 2
            or len(self.conversion_factors) != 2
        ):
            warn(msg, debugging.SuspiciousUsageWarning)

    def constraint_group(self):
        return LinkBlock


class LinkBlock(ScalarBlock):
    r"""Block for the relation of nodes with type
    :class:`~oemof.solph.components.experimental.Link`

    Note: This component is experimental. Use it with care.

    **The following constraints are created:**

    .. _Link-equations:

    .. math::
        &
        (1) \qquad P_{\mathrm{in},n}(p, t) = c_n(t)
        \times P_{\mathrm{out},n}(p, t)
            \quad \forall t \in T, \forall n in {1,2} \\
        &

    """
    CONSTRAINT_GROUP = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _create(self, group=None):
        """Creates the relation for the class:`Link`.

        Parameters
        ----------
        group : list
            List of oemof.solph.components.experimental.Link objects for which
            the relation of inputs and outputs is createdBuildAction
            e.g. group = [link1, link2, link3, ...]. The components inside
            the list need to hold an attribute `conversion_factors` of type
            dict containing the conversion factors for all inputs to outputs.
        """
        if group is None:
            return None

        m = self.parent_block()

        all_conversions = {}
        for n in group:
            all_conversions[n] = {
                k: v for k, v in n.conversion_factors.items()
            }

        self.LINKS = Set(initialize=[g for g in group])

        def _input_output_relation(block):
            for p, t in m.TIMEINDEX:
                for n, conversion in all_conversions.items():
                    for cidx, c in conversion.items():
                        try:
                            expr = (
                                m.flow[n, cidx[1], p, t]
                                == c[t] * m.flow[cidx[0], n, p, t]
                            )
                        except ValueError:
                            raise ValueError(
                                "Error in constraint creation",
                                "from: {0}, to: {1}, via: {2}".format(
                                    cidx[0], cidx[1], n
                                ),
                            )
                        block.relation.add((n, cidx[0], cidx[1], p, t), expr)

        self.relation = Constraint(
            [
                (n, cidx[0], cidx[1], p, t)
                for p, t in m.TIMEINDEX
                for n, conversion in all_conversions.items()
                for cidx, c in conversion.items()
            ],
            noruleinit=True,
        )
        self.relation_build = BuildAction(rule=_input_output_relation)
