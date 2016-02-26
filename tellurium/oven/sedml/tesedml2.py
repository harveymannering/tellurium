# -*- coding: utf-8 -*-
"""
Tellurium SED-ML support.

This module reads SED-ML files ('.sedml' extension) or archives ('.sedx' extension)
and generates executable python code.
To work with phrasedml files convert these to SED-ML first (see `tephrasedml.py`).

::

    # execute example sedml
    import tellurium.tesedml as s2p
    ret = s2p.sedmlToPython('example.sedml')
    exec ret

    # execute sedml archive (sedx)
    import SedmlToRr as s2p
    ret = s2p.sedmlToPython("example.sedx")
    exec ret


SED-ML is build of five main classes, which are translated in python code:
    the Model Class,
    the Simulation Class,
    the Task Class,
    the DataGenerator Class,
    and the Output Class.

The Model Class
    The Model class is used to reference the models used in the simulation experiment.
    SED-ML itself is independent of the model encoding underlying the models. The only
    requirement is that the model needs to be referenced by using an unambiguous identifier
    which allows for finding it, for example using a MIRIAM URI. To specify the language in
    which the model is encoded, a set of predefined language URNs is provided.
    The SED-ML Change class allows the application of changes to the referenced models,
    including changes on the XML attributes, e.g. changing the value of an observable,
    computing the change of a value using mathematics, or general changes on any XML element
    of the model representation that is addressable by XPath expressions, e.g. substituting
    a piece of XML by an updated one.

The Simulation Class
    The Simulation class defines the simulation settings and the steps taken during simulation.
    These include the particular type of simulation and the algorithm used for the execution of
    the simulation; preferably an unambiguous reference to such an algorithm should be given,
    using a controlled vocabulary, or ontologies. One example for an ontology of simulation
    algorithms is the Kinetic Simulation Algorithm Ontology KiSAO. Further information encodable
    in the Simulation class includes the step size, simulation duration, and other
    simulation-type dependent information.

The Task Class
    SED-ML makes use of the notion of a Task class to combine a defined model (from the Model class)
    and a defined simulation setting (from the Simulation class). A task always holds one reference each.
    To refer to a specific model and to a specific simulation, the corresponding IDs are used.

The DataGenerator Class
    The raw simulation result sometimes does not correspond to the desired output of the simulation,
    e.g. one might want to normalise a plot before output, or apply post-processing like mean-value calculation.
    The DataGenerator class allows for the encoding of such post-processings which need to be applied to the
    simulation result before output. To define data generators, any addressable variable or parameter
    of any defined model (from instances of the Model class) may be referenced, and new entities might
    be specified using MathML definitions.

The Output Class
    The Output class defines the output of the simulation, in the sense that it specifies what shall be
    plotted in the output. To do so, an output type is defined, e.g. 2D-plot, 3D-plot or data table,
    and the according axes or columns are all assigned to one of the formerly specified instances
    of the DataGenerator class.
"""
from __future__ import print_function, division
import os
import sys
import warnings
import libsedml
import libsbml
from jinja2 import Environment, FileSystemLoader
import zipfile
import sedmlfilters
from tellurium import getTelluriumVersion
import datetime
from tellurium.tecombine import CombineTools
from collections import namedtuple


# Change default encoding to UTF-8
# We need to reload sys module first, because setdefaultencoding is available only at startup time
reload(sys)
sys.setdefaultencoding('utf-8')


def sedml_to_python(input):
    """ Convert sedml file to python code.

    Deprecated: use sedmlToPython()

    :param inputstring:
    :type inputstring:
    :return:
    :rtype:
    """
    warnings.warn('Use sedmlToPython instead, will be removed in v1.4',
                  DeprecationWarning, stacklevel=2)
    return sedmlToPython(input)


def sedmlToPython(inputStr):
    """ Convert sedml file to python code.

    :param inputstring: full path name to SedML model or SED-ML string
    :type inputstring: path
    :return: contents
    :rtype:
    """
    factory = SEDMLCodeFactory(inputStr)
    return factory.toPython()


class SEDMLTools(object):
    """ Helper functions to work with sedml. """

    INPUT_TYPE_STR = 'SEDML_STRING'
    INPUT_TYPE_FILE_SEDML = 'SEDML_FILE'
    INPUT_TYPE_FILE_COMBINE = 'COMBINE_FILE'  # includes .sedx archives

    @classmethod
    def checkSEDMLDocument(cls, doc):
        """ Checks the SedDocument for errors.
        Raises IOError if error exists.
        :param doc:
        :type doc:
        """
        if doc.getErrorLog().getNumFailsWithSeverity(libsedml.LIBSEDML_SEV_ERROR) > 0:
            raise IOError(doc.getErrorLog().toString())

    @classmethod
    def readSEDMLDocument(cls, inputStr):
        """ Parses SedMLDocument from given input.

        :return: dictionary of SedDocument, inputType and working directory.
        :rtype: {doc, inputType, workingDir}
        """
        # SEDML-String
        try:
            from xml.etree import ElementTree
            x = ElementTree.fromstring(inputStr)
            # is parsable xml string
            doc = libsedml.readSedMLFromString(inputStr)
            inputType = cls.INPUT_TYPE_STR

        # SEDML-File
        except ElementTree.ParseError:
            if not os.path.exists(inputStr):
                raise IOError("File not found:", inputStr)

            filename, extension = os.path.splitext(os.path.basename(inputStr))

            # SEDML file
            if extension in [".sedml", '.xml']:
                inputType = cls.INPUT_TYPE_FILE_SEDML
                doc = libsedml.readSedMLFromFile(inputStr)
                cls.checkSEDMLDocument(doc)
                # working directory is where the sedml file is
                workingDir = os.path.dirname(os.path.realpath(inputStr))

            # Archive
            elif zipfile.is_zipfile(inputStr):
                archive = inputStr
                inputType = cls.INPUT_TYPE_FILE_COMBINE

                # in case of sedx and combine a working directory is created
                # in which the files are extracted
                workingDir = os.path.join(os.path.dirname(os.path.realpath(inputStr)), '_te_{}'.format(filename))
                # extract the archive to working directory
                CombineTools.extractArchive(archive, workingDir)
                # get SEDML files from archive
                # FIXME: there could be multiple SEDML files in archive (currently only first used)
                sedmlFiles = CombineTools.filePathsFromExtractedArchive(workingDir)
                if len(sedmlFiles) == 0:
                    raise IOError("No SEDML files found in archive.")
                if len(sedmlFiles) > 1:
                    warnings.warn("More than one sedml file in archive, only processing first one.")
                doc = libsedml.readSedMLFromFile(sedmlFiles[0])
                cls.checkSEDMLDocument(doc)

        return {'doc': doc,
                'inputType': inputType,
                'workingDir': workingDir}


    @staticmethod
    def resolveModelChanges(doc):
        """ Resolves the original source model and full change lists for models.

         Going through the tree of model upwards until root is reached and
         collecting changes on the way (example models m* and changes c*)
         m1 (source) -> m2 (c1, c2) -> m3 (c3, c4)
         resolves to
         m1 (source) []
         m2 (source) [c1,c2]
         m3 (source) [c1,c2,c3,c4]
         The order of changes is important (at least between nodes on different
         levels of hierarchies), because later changes of derived models could
         reverse earlier changes.

         Uses recursive search strategy, which should be okay as long as the model tree hierarchy is
         not getting to big.
         """
        # initial dicts (handle source & change information for single node)
        model_sources = {}
        model_changes = {}

        for m in doc.getListOfModels():
            mid = m.getId()
            source = m.getSource()
            model_sources[mid] = source
            changes = []
            # store the changes unique for this model
            for c in m.getListOfChanges():
                changes.append(c)
            model_changes[mid] = changes

        # recursive search for original model and store the
        # changes which have to be applied in the list of changes
        def findSource(mid, changes):

            # mid is node above
            if mid in model_sources:
                # add changes for node
                for c in model_changes[mid]:
                    changes.append(c)
                # keep looking deeper
                return findSource(model_sources[mid], changes)
            # the source is no longer a key in the sources, it is the source
            return mid, changes

        all_changes = {}

        mids = [m.getId() for m in doc.getListOfModels()]
        for mid in mids:
            source, changes = findSource(mid, changes=list())
            model_sources[mid] = source
            all_changes[mid] = changes[::-1]

        return model_sources, all_changes


    @staticmethod
    def resolveSimulations(doc):
        """ Resolves all the settings for the simulation.

        The parsed algorithm settings are stores in dictionaries which allow than to
        easily set the simulation options and the integrator settings.
        Two dictionaries are created:
            simulate_settings: keyword arguments for simulate
            integrator_setting

        :return:
        :rtype:
        """
        sids = [sim.getId() for sim in doc.getListOfSimulations()]
        print(sids)
        simulate_settings = {}
        integrator_settings = {}
        algorithms = {}
        for sim in doc.getListOfSimulations():
            sid = sim.getId()
            alg = sim.getAlgorithm()
            algorithms[sid] = alg
            kisaoId = alg.getKisaoID()
            print(kisaoId)

        print(algorithms)

        return None


class SEDMLCodeFactory(object):
    """ Code Factory generating executable code.
        The following SED-ML constructs are currently NOT supported:

        - Change.RemoveXML
        - Change.AddXML
        - Change.ChangeXML
        - Change.ComputeChange

        - Range.FunctionalRange



        TODO: Handle MathML with variables and parameters (evaluation)
        - functional range
        - data generators
        - changes

        TODO: Handle general XML transformations

    """

    # template location
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

    def __init__(self, inputStr):
        """ Create CodeFactory for given input.
        :param inputStr:
        :type inputStr:
        :return:
        :rtype:
        """
        self.inputStr = inputStr
        info = SEDMLTools.readSEDMLDocument(inputStr)
        self.doc = info['doc']
        self.inputType = info['inputType']
        self.workingDir = info['workingDir']

        # parse the models (resolve the source models & the applied changes for all models)
        model_sources, model_changes =SEDMLTools.resolveModelChanges(self.doc)
        self.model_sources = model_sources
        self.model_changes = model_changes

    def __str__(self):
        """ Print Input
        :return:
        :rtype:
        """
        lines = [
            '{}'.format(self.__class__),
            'doc: {}'.format(self.doc),
            'workingDir: {}'.format(self.workingDir),
            'inputType: {}'.format(self.inputType)
        ]
        if self.inputType != SEDMLTools.INPUT_TYPE_STR:
            lines.append('input: {}'.format(self.inputStr))
        return '\n'.join(lines)

    def toPython(self, python_template='tesedml_template.py'):
        """ Create python code by rendering the python template.
        Uses the information in the SED-ML document to create
        python code

        Renders the respective template.

        :return: returns the rendered template
        :rtype: str
        """
        # template environment
        env = Environment(loader=FileSystemLoader(self.TEMPLATE_DIR),
                          extensions=['jinja2.ext.autoescape'],
                          trim_blocks=True,
                          lstrip_blocks=True)

        # additional filters
        for key in sedmlfilters.filters:
             env.filters[key] = getattr(sedmlfilters, key)
        template = env.get_template(python_template)
        env.globals['modelChangeToPython'] = self.modelChangeToPython
        env.globals['taskToPython'] = self.taskToPython

        # timestamp
        time = datetime.datetime.now()
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S')

        # Context
        c = {
            'version': getTelluriumVersion(),
            'timestamp': timestamp,
            'factory': self,
            'doc': self.doc,
            'model_sources': self.model_sources,
            'model_changes': self.model_changes,
        }
        return template.render(c)

    @staticmethod
    def modelChangeToPython(model, change):
        """ Creates the apply change python string for given model and change.

        Currently only a very limited subset of model changes is supported.
        Namely changes of parameters and concentrations within a SedChangeAttribute.

        :param model: given model
        :type model: SedModel
        :param change: model change
        :type change: SedChange
        :return:
        :rtype: str
        """
        lines = []
        mid = model.getId()

        if change.getTypeCode() == libsedml.SEDML_CHANGE_ATTRIBUTE:

            # resolve target change
            xpath = change.getTarget()
            value = change.getNewValue()
            lines.append("# {} {}".format(xpath, value))
            lines.append(SEDMLCodeFactory.targetToPython(xpath, value, modelId=mid))

        elif change.getTypeCode() == libsedml.SEDML_CHANGE_COMPUTECHANGE:
            lines.append("# Unsupported change: {}".format(change.getElementName()))
            # TODO: implement

        elif change.getTypeCode() in [libsedml.SEDML_CHANGE_REMOVEXML,
                                      libsedml.SEDML_CHANGE_ADDXML,
                                      libsedml.SEDML_CHANGE_CHANGEXML]:
            lines.append("# Unsupported change: {}".format(change.getElementName()))
            # TODO: implement
        else:
            lines.append("# Unsupported change: {}".format(change.getElementName()))

        return '\n'.join(lines)

    @staticmethod
    def taskToPython(doc, task):
        """ Create python for arbitrary task (repeated or simple).

        :param doc:
        :type doc:
        :param task:
        :type task:
        :return:
        :rtype:
        """
        lines = []
        taskType = task.getTypeCode()

        # <SIMPLE TASK>
        if taskType == libsedml.SEDML_TASK:
            selections = SEDMLCodeFactory.selectionsForTask(doc=doc, task=task)
            lines.extend(SEDMLCodeFactory.subtaskToPython(doc=doc, task=task, selections=selections))

        # <REPEATED TASK>
        elif taskType == libsedml.SEDML_TASK_REPEATEDTASK:
            resetModel = task.getResetModel()
            rangeId = task.getRangeId()

            for subtask in task.getListOfSubTasks():
                t = doc.getTask(subtask.getTask())  # get real task by belonging to subtask
                mid = t.getModelReference()

                # get master range
                masterRange = task.getRange(rangeId)

                # create range to iterate
                import numpy as np
                if masterRange.getTypeCode() == libsedml.SEDML_RANGE_UNIFORMRANGE:
                    rStart = masterRange.getStart()
                    rEnd = masterRange.getEnd()
                    rPoints = masterRange.getNumberOfPoints()
                    rType = masterRange.getType()
                    if rType == 'Linear':
                        __range = np.linspace(start=rStart, stop=rEnd, num=rPoints)
                    elif rType == 'Log':
                        __range = np.logspace(start=rStart, stop=rEnd, num=rPoints)
                    else:
                        warnings.warn("Unsupported range type in UniformRange: {}".format(rType))

                elif masterRange.getTypeCode() == libsedml.SEDML_RANGE_VECTORRANGE:
                    __range = np.zeros(shape=[1, masterRange.getNumValues()])
                    for k, v in masterRange.getValues():
                        __range[1, k] = v

                elif masterRange.getTypeCode() == libsedml.SEDML_RANGE_FUNCTIONALRANGE:
                    # TODO: implement
                    warnings.warn('FunctionalRange NOT IMPLEMENTED')

                # ---------------------------
                # iterate over range
                # ---------------------------
                lines.append("__range = {}".format(list(__range)))
                lines.append("{} = [None] * len(__range)".format(task.getId()))
                lines.append("for k, value in enumerate(__range):")

                # we have to intent all lines from now on (in for loop)
                forLines = []

                # resetModel
                if resetModel:
                    forLines.append("{}.reset()".format(mid))

                # apply changes
                for change in task.getListOfTaskChanges():
                    if change.getElementName() != "setValue":
                        warnings.warn("Only setValue changes are supported at this time")
                        return

                    xpath = change.getTarget()
                    forLines.append(SEDMLCodeFactory.targetToPython(xpath, value="value", modelId=mid))

                # Run single repeat
                # TODO: implement multiple subtasks
                resultVariable = "{}[k]".format(task.getId())
                selections = SEDMLCodeFactory.selectionsForTask(doc=doc, task=task)
                forLines.extend(SEDMLCodeFactory.subtaskToPython(doc, task=t,
                                                                 selections=selections,
                                                                 resultVariable=resultVariable))
                # ---------------------------
                # add the intendend for lines
                lines.extend('    ' + line for line in forLines)
        else:
            lines.append("# Unsupported task: {}".format(taskType))
        return "\n".join(lines)

    @staticmethod
    def subtaskToPython(doc, task, selections, resultVariable=None):
        """ Creates the simulation python code for a given task.

            cvode (19; the default for uniform time course simulations)
            gillespie (241; the default for stochastic time course simulations)
            steadystate (407; the default for steady state simulations)
            rk4 (32; 4th-order Runge-Kutta)
            rk45 (435; embedded Runge-Kutta)
        """
        # TODO: handle: ".conservedMoietyAnalysis = False/True"
        lines = []

        mid = task.getModelReference()
        sid = task.getSimulationReference()
        simulation = doc.getSimulation(sid)
        simType = simulation.getTypeCode()
        algorithm = simulation.getAlgorithm()
        kisao = algorithm.getKisaoID()

        # Check if supported algorithm
        if not SEDMLCodeFactory.isSupportedKisaoIDForSimulation(kisao=kisao, simType=simType):
            lines.append("# Unsupported KisaoID {} for Algorithm {}".format(kisao, simType))
            return "\n".join(lines)

        # Set integrator
        integratorName = SEDMLCodeFactory.getIntegratorNameForKisaoID(kisao)
        if not integratorName:
            lines.append("# No integrator for KisaoID {} in tellurium".format(kisao))
            return "\n".join(lines)
        lines.append("{}.setIntegrator('{}')".format(mid, integratorName))

        # Set integrator settings (AlgorithmParameters)
        for par in algorithm.getListOfAlgorithmParameters():
            lines.append(SEDMLCodeFactory.algorithmParameterToPython(par))

        # handle result variable
        if resultVariable is None:
            resultVariable = task.getId()

        # -------------------------------------------------------------------------
        # <UNIFORM TIMECOURSE>
        # -------------------------------------------------------------------------
        if simType == libsedml.SEDML_SIMULATION_UNIFORMTIMECOURSE:
            lines.append("{}.timeCourseSelections = {}".format(mid, list(selections)))

            initialTime = simulation.getInitialTime()
            outputStartTime = simulation.getOutputStartTime()
            outputEndTime = simulation.getOutputEndTime()
            numberOfPoints = simulation.getNumberOfPoints()

            # throw some points away
            if abs(outputStartTime - initialTime) > 1E-6:
                lines.append("{}.simulate(start={}, end={}, points=2)".format(
                                    mid, initialTime, outputStartTime))
            # real simulation
            lines.append("{} = {}.simulate(start={}, end={}, steps={})".format(
                                    resultVariable, mid, outputStartTime, outputEndTime, numberOfPoints))
        # -------------------------------------------------------------------------
        # <ONESTEP>
        # -------------------------------------------------------------------------
        elif simType == libsedml.SEDML_SIMULATION_ONESTEP:
            lines.append("{}.timeCourseSelections = {}".format(mid, list(selections)))
            step = simulation.getStep()
            lines.append("{} = {}.simulate(start=0.0, end={}, points=2)".format(resultVariable, mid, step))

        # -------------------------------------------------------------------------
        # <STEADY STATE>
        # -------------------------------------------------------------------------
        elif simType == libsedml.SEDML_SIMULATION_STEADYSTATE:
            lines.append("{}.steadyStateSelections = {}".format(mid, list(selections)))
            lines.append("{} = {}.steadyState()".format(resultVariable, mid))

        # -------------------------------------------------------------------------
        # <OTHER>
        # -------------------------------------------------------------------------
        else:
            lines.append("# Unsupported simulation: {}".format(simType))

        return lines

    @staticmethod
    def selectionsForTask(doc, task):
        """ Populate variable lists from the data generators for the given task.

        These are the timeCourseSelections and steadyStateSelections
        in RoadRunner.

        Search all data generators for variables which have to be part of the simulation.
        """
        selections = set()
        for dg in doc.getListOfDataGenerators():
            for var in dg.getListOfVariables():
                # either has not task reference or not for the current task
                if var.getTaskReference() != task.getId():
                    continue

                # symbol field of variable is set
                if var.isSetSymbol():
                    cvs = var.getSymbol()
                    astr = cvs.rsplit("symbol:")
                    astr = astr[1]
                    selections.add(astr)

                elif var.isSetTarget():
                    cvt = var.getTarget()    # target field of variable is set
                    astr = cvt.rsplit("@id='")
                    astr = astr[1]
                    astr = astr[:-2]
                    if 'species' in cvt:
                        selections.add('[{}]'.format(astr))
                    else:
                        selections.add('{}'.format(astr))
                else:
                    warnings.warn("Unrecognized data generator variable")
        return selections

    @staticmethod
    def isSupportedKisaoIDForSimulation(kisao, simType):
        """ Test if Algorithm Kisao Id is supported for simulation.

            KISAO:0000433 : CVODE-like method
            KISAO:0000019 : CVODE
            KISAO:0000241 : Gillespie-like method
            KISAO_0000064 : Runge-Kutta based method
            KISAO_0000032 : explicit fourth-order Runge-Kutta method
            KISAO_0000435 : embedded Runge-Kutta 5(4) method

        :return:
        :rtype: bool
        """
        supported = []
        if simType == libsedml.SEDML_SIMULATION_UNIFORMTIMECOURSE:
            supported = ['KISAO:0000433', 'KISAO:0000019', 'KISAO:0000241', 'KISAO:0000032', 'KISAO:0000435', 'KISAO_0000064']
        elif simType == libsedml.SEDML_SIMULATION_ONESTEP:
            supported = ['KISAO:0000433', 'KISAO:0000019', 'KISAO:0000241', 'KISAO:0000032', 'KISAO:0000435', 'KISAO_0000064']
        elif simType == libsedml.SEDML_SIMULATION_STEADYSTATE:
            supported = ['KISAO:0000099', 'KISAO:0000407']
        return kisao in supported

    @staticmethod
    def getIntegratorNameForKisaoID(kid):
        """ RoadRunner integrator name for algorithm KisaoID.

        :param kid: KisaoID
        :type kid: str
        :return: RoadRunner integrator name.
        :rtype: str
        """
        # cvode & steady state are mapped to cvode
        if kid in ['KISAO:0000433', 'KISAO:0000019', 'KISAO:0000407']:
            return 'cvode'
        elif kid == 'KISAO:0000241':
            return 'gillespie'
        elif kid == 'KISAO:0000032':
            return 'rk4'
        elif kid in ['KISAO:0000435', 'KISAO_0000064']:
            return 'rk45'
        else:
            return None

    @staticmethod
    def algorithmParameterToPython(par):
        """ Create python code for algorithm parameter.

        Sets the algorithm parameter for the current integrator.

            relative_tolerance (209; the relative tolerance)
            absolute_tolerance (211; the absolute tolerance)
            maximum_bdf_order (220; the maximum BDF (stiff) order)
            maximum_adams_order (219; the maximum Adams (non-stiff) order)
            maximum_num_steps (415; the maximum number of steps that can be taken before exiting)
            maximum_time_step (467; the maximum time step that can be taken)
            minimum_time_step (485; the minimum time step that can be taken)
            initial_time_step (332; the initial value of the time step for algorithms that change this value)
            variable_step_size (107; whether or not the algorithm proceeds with an adaptive step size or not)
            maximum_iterations (486; the maximum number of iterations the algorithm should take before exiting)
            minimum_damping (487; minimum damping value)
            seed (488; the seed for stochastic runs of the algorithm)
        """
        kid = par.getKisaoID()
        value = par.getValue()

        if kid == 'KISAO_0000209':
            key = 'relative_tolerance'
        elif kid == 'KISAO_0000211':
            key = 'relative_tolerance'
        elif kid == 'KISAO_0000220':
            key = 'maximum_bdf_order'
        elif kid == 'KISAO_0000219':
            key = 'maximum_adams_order'
        elif kid == 'KISAO_0000415':
            key = 'maximum_num_steps'
        elif kid == 'KISAO_0000467':
            key = 'maximum_time_step'
        elif kid == 'KISAO_0000485':
            key = 'minimum_time_step'
        elif kid == 'KISAO_0000332':
            key = 'initial_time_step'
        elif kid == 'KISAO_0000107':
            key = 'variable_step_size'
        elif kid == 'KISAO_0000486':
            key = 'maximum_iterations'
        elif kid == 'KISAO_0000487':
            key = 'maximum_damping'
        elif kid == 'KISAO_0000488':
            key = 'seed'
        # set the setting
        if key:
            return "{}{}.getIntegrator().setValue({}, {})".format(key, value)
        if not key:
            return "{}# Unsupported AlgorithmParameter: {} = {})".format(kid, value)

    @staticmethod
    def targetToPython(xpath, value, modelId):
        """ Creates python line for given xpath target and value.
        :param xpath:
        :type xpath:
        :param value:
        :type value:
        :return:
        :rtype:
        """
        target = SEDMLCodeFactory.resolveTargetFromXPath(xpath)

        # parameter value change
        if target.type == "parameter":
            line = ("{}['{}'] = {}".format(modelId, target.id, value))
        # species concentration change
        elif target.type == "species":
            line = ("{}['init([{}])'] = {}".format(modelId, target.id, value))
        else:
            line = ("# Unsupported target: {}".format(xpath))
        return line

    @staticmethod
    def resolveTargetFromXPath(xpath):
        """ Resolve the model target to model identifier.

        :param xpath:
        :type xpath:
        :return:
        :rtype:
        """
        # FIXME: getting of sids, pids not very robust
        # TODO: handle more cases (rules, reactions, ...)
        Target = namedtuple('Target', 'id type')

        def getId(xpath):
            xpath = xpath.rsplit("id=\'", 1)[1]
            return xpath.rsplit("\'", 1)[0]

        # parameter value change
        if ("model" in xpath) and ("parameter" in xpath):
            return Target(getId(xpath), 'parameter')

        # species concentration change
        elif ("model" in xpath) and ("species" in xpath):
            return Target(getId(xpath), 'species')

    @staticmethod
    def dataGeneratorToPython(doc, generator):
        """ Create the variable from the data generators and the simulations. """

        """
        variablesDictionary = []      # matching pairs of sedml variable ID and sbml variable ID
        variablesList = []            # the IDs of the sbml variables, non duplicate entries
        bFoundAtLeastOneTask = False

        for e in range(0,sedmlDoc.getNumTasks()):
            task1 = sedmlDoc.getTask(e)

            # repeated task
            if task1.getElementName() == "repeatedTask":
                for i in range(0, task1.getNumSubTasks()):
                    task2 = task1.getSubTask(i)     # the subtask which points to the real task we need to call repeatedly for each value in range
                    task2 = task2.getTask()         # the Id of the real task
                    task2 = sedmlDoc.getTask(task2) # get real task by Id
                    if task2.getModelReference() != currentModel.getId():
                        continue
                    aRange = task1.getRange(0)       # we assume one single master range - we don't know how to deel flatten
                    if aRange.getElementName() != "uniformRange":
                        print("# Only uniformRange ranges are supported at this time")
                        continue
                    variablesDictionary = []
                    variablesList = []
                    # need to use the RepeatedTask because the data generators refer to it
                    populateVariableLists(sedmlDoc, task1, variablesList, variablesDictionary)
                    # for each point in the range we compute the new values of the variables affected
                    # and generate a task
                    for j in range(0, aRange.getNumberOfPoints()):
                        # need to use both the real Task (task2) because it has the reference to model and simulation
                        # and the repeated task (task1) because its Id is used for generating the flattened Id's
                        generateDataLoop(sedmlDoc, currentModel, task2, variablesList, variablesDictionary, j, task1, dataGeneratorsList)
                        bFoundAtLeastOneTask = True
                        print("")

            # not a repeated task
            else:
                if task1.getModelReference() != currentModel.getId():
                    continue
                variablesDictionary = []
                variablesList = []
                populateVariableLists(sedmlDoc, task1, variablesList, variablesDictionary)
                if len(variablesList) == 0:
                    continue
                generateDataLoop(sedmlDoc, currentModel, task1, variablesList, variablesDictionary, -1)
                bFoundAtLeastOneTask = True

        """

    def executePython(self):
        """ Executes created python code.
        See :func:`createpython`
        """
        execStr = self.toPython()
        try:
            # This calls exec. Be very sure that nothing bad happens here.
            exec execStr
        except Exception as e:
            raise e

##################################################################################################
if __name__ == "__main__":
    import os
    from tellurium.tests.testdata import sedmlDir, sedxDir, psedmlDir

    for fname in ['app2sim.sedml',
                  # 'asedml3repeat.sedml',
                  # 'asedmlComplex.sedml',
                  # 'BioModel1_repressor_activator_oscillations.sedml'
                ]:

        sedml_input = os.path.join(sedmlDir, fname)
        factory = SEDMLCodeFactory(sedml_input)
        # create python
        python_str = factory.toPython()
        print('#'*80)
        print(python_str)
        print('#'*80)
        # create python file
        with open(sedml_input + '.py', 'w') as f:
            f.write(python_str)
        # execute python
        factory.executePython()

    exit()

    # test file
    sedml_input = os.path.join(sedxDir, 'app2sim.sedx')
    # resolve models
    factory = SEDMLCodeFactory(sedml_input)

    # ------------------------------------------------------
    def testInput(sedmlInput):
        """ Test function run on inputStr. """
        print('\n', '*'*100)
        print(sedmlInput)
        print('*'*100)
        factory = SEDMLCodeFactory(sedmlInput)
        print(factory)

    # ------------------------------------------------------
    # Check sed-ml files
    for fname in sorted(os.listdir(sedmlDir)):
        if fname.endswith(".sedml"):
            testInput(os.path.join(sedmlDir, fname))

    # Check sedx archives
    for fname in sorted(os.listdir(sedxDir)):
        if fname.endswith(".sedx"):
            testInput(os.path.join(sedxDir, fname))

    # Check phrasedml files
    for fname in sorted(os.listdir(psedmlDir)):
        if fname.endswith(".psedml"):
            pass
            # testInput(os.path.join(psedmlDir, fname))

    # ------------------------------------------------------

    """

    """

    """
    sim = libsedml.SedSimulation()
    sim.getTypeCode()
    libsedml.SEDML_SIMULATION_ONESTEP
    """
