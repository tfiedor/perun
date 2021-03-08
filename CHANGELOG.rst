Changelog
=========

HEAD
----

**To be included in next release**

  - Update README with additional install instructions
  - SystemTap and BCC instructions for Ubuntu and Fedora 


0.20 (2021-03-05)
-----------------

`commit: 12c181f1a3c94699ee2818f996ee2651a7e30578`

**Add optimizations of collect process**

  - add engines to the Tracer architecture
  - add eBPF instrumentation support to Tracer (using BCC)
  - add Optimization module to the collection process
  - add several optimization methods to the Optimization module
  - update Tracer for Python 3.8

0.19 (2021-02-08)
-----------------

`commit: 07a6c7a54392ae245964956ed69a56f050f89fca`

**Update Perun to Python 3.8+**

  - add timeout to running external programs
  - optimize getting of gcov version
  - fix issues in fuzzing tests
  - remove dependencies of clang
  - update Perun to higher versions of gcc (4.9+) and Python (3.8+)
  - fix minor issues and incompatibilities
  - add lazy initialization of mathplotlib
  - remove usage of re.Scanner which seems to segfault on newer versions
  - remove heat map and ncurses (will be reimplemented in near future)

0.18.3-hotfix2 (2020-08-31)
--------------------------

`commit: ac5e719b483f62b56e5273afc165335c46a68f76`

  - update the acknowledgements in README

0.18.3-hotfix (2020-05-11)
--------------------------

`commit: 3998d715041f624b836bef46b123d2139a8528fe`

  - fix two minor issues in average amount threshold check (fix for profiles without amounts and to soften the dependency on numpy.float64)

0.18.3 (2020-03-20)
-------------------

`commit: 7b19f07eb2612899be96dfaa24b5912705c6ae42`

**Extend the Perun and fix selected issues**

  - add helper assertions for tests available in `asserts.py` file
  - remove useless fixtures (Helpers), move the helpers functions to isolate package
  - categorize test data to several directories
  - add automatical lookup of (in)dependent variable as default for selected commands (postprocess, etc.)
  - add crash dump in case of unexpected error (can be suppressed by `--dev-mode` option)
  - update the documentation with latest features and fix missing stuff
  - add external generator of the
  - fix the issue with backward incompatible repositories which contained profiles with 'params' instead of 'args'
  - fix the issue with loading certain parts of degradation changes as strings (instead of doubles)
  - fix the issue with loading degradation changes which contained less information than in the new versions (missing the `drate`)
  - fix other minor issues
  - fix minor issues in fuzzing
  - fix issue with clang-3.5 binary missing in systems (add the binary)
  - fix the incorrectly printed trace

0.18.2 (2020-02-13)
-------------------

`commit: c68ba580d53b6e40df48bcef4e2bd6af3c9754e6`

**Fix errors in novel check methods**

  - fix selected errors in novel check methods
  - automatically remove testing files
  - extend the collection process with specifying custom name

0.18.1 (2020-02-13)
-------------------

`commit: 5166ec167bddc5e72877029dc19f1302aaa8cb8b`

**Refactor trace collector**

  - refactor trace collector
  - extend trace collector with watchdog module
  - selected temporary files moved to .perun directory structure
  - add diagnostic mode for trace collector
  - add locking module to perun logic
  - add diagnostic mode to tracer
  - ignore tracer tests in codecoverage

0.18 (2020-02-11)
-----------------

`commit: 252078825559d67b6c915ab01827a9433af92dfa`

**Add performance fuzz-testing**

  - add ``perun fuzz`` mode implementing mutation based fuzzer. See :ref:`fuzzing-overview` for more details.

0.17.4 (2020-01-28)
-------------------

`commit: cfb264ed53155a4aabf3874729c2c573533b0d1d`

**Add tabular view**

  - add tableof view module
  - add conversion functions of models to dataframe
  - add headers to tableof view
  - add formats to tableof view
  - add sorting to tableof view
  - add filtering to tableof view
  - add two modes of tableof (resources and models)
  - fix minor bug in bounds collector (unknown collector type)
  - fix templates for generating units

0.17.3 (2020-01-09)
-------------------

`commit: f3819834803b1eed878feeee51b697b260988c65`

**Add Loopus collector in Perun**

  - fix an issue in profiles which contained only persistent properties
  - add bounds collector, wrapper over Loopus tool

0.17.2 (2019-08-16)
-------------------

`commit: d82d15ec5635dacf8027311e44aa65b4776dc8fb`

**Improve the runner logic**

  - extract cmd, args and workload to Executable class
  - remove ``--remove-all`` argument in ``perun rm``
  - add support for removing profiles from pending jobs through perun
  - improve the output of `perun rm` command
  - extract CLI groups to isolate modules
  - add caching to selected vcs commands
  - fix untested bug in degradation check
  - rename warmup parameter in `time` to ``--warmup``
  - lower the number of warmup and repetitions for time collector during tests
  - remove filter postprocessor (did nothing)
  - add signal handling to runner (authored by Jirka Pavela)

0.17.1 (2019-07-24)
-------------------

`commit: e2fad3cd2ac22f17aa7abfe4375d9940eb9f2847`

**Add new degradation detection methods**

  - add new detection methods for parametric and non-parametric models
  - add **Integral Comparison** detection method, which computes the integrals under models
  - add **Local Statistics** detection method, which analyses the various statistics in intervals of models
  - refactor various minor issues in postprocessing logic
  - add new strategies for detecting performance changes

0.17 (2019-07-09)
-----------------

`commit: e6b1e88d766d93cdab4f114464df51114d6415a8`

**Optimize profile format**

  - make profile format more compact
  - fix minor issue in fast check
  - extract selected functions from query to profile object

0.16.9-hotfix (2019-06-18)
--------------------------

`commit: 126473caba3685878bf79f687115023918d5048a`

**Hotfix issue in Makefile**

 - hotfix issue in Makefile

0.16.9 (2019-06-18)
-------------------

`commit: 8e7228deb81cdfacfea7e7273fd25e70503cbe2b`

**Add CLI for stats manipulation**

  - refactor the perun stats module
  - extend the stats module with a CLI
  - add new operations (list, delete, ...) to the stats module

0.16.8 (2019-05-18)
-------------------

`commit: 05d7275cb5f00183a72f8428bc4aaba0420bb73b`

**Extend perun instances with temporaries**

  - add new logic module that allows to store temporary files in separate directory (.perun/tmp)

0.16.7-hotfix (2019-04-15)
--------------------------

`commit: 686ea87a64d845b215474193f879db0240c05732`

**Hotfix Jinja potential vulnerability**

  - hotfix Jinja potential vulnerability

0.16.7 (2019-04-15)
-------------------

`commit: 4152091bc4c2e5d1553ebccfef059d8153255aba`

**Extend perun instances with stats**

  - add new logic module that allows to store stats for profiles in separate directory (.perun/stats)

0.16.6 (2019-03-25)
-------------------

`commit: 18870d9d5853726d5cc966962d275111e451ab06`

**Improve the quality of life of Perun**

  - fix minor bug in storing changes
  - extracted index entry specific functions to isolate class (in order to create new versions)
  - implement index v2.0, codename FastSloth
  - switch to working with index v2.0 (index v1.0 is still supported, however, everything is saved as 2.0)
  - minor refactors
  - optimize loading of the profile info for both registered and pending profiles (yields huge performance boost)
  - add `--force` option to `perun add` which will force the add (d'oh)
  - add printing of trace if `perun -vv` is set in cli (i.e. the verbosity is of level 2+)
  - rename 'params' in profile to 'args' since it complies to other parts of code
  - refactor minor issues, enhance error messages and exception handling

0.16.5 (2019-03-22)
-------------------

`commit: a2bd359479920178cfed1a0de779ef6fa5f4d4ac`

**Revive complexity collector**

  - revive the complexity collector
  - increase the test coverage of complexity collector
  - update the complexity collector to comply with latest version of Perun

`commit: 983b02ca54faa66941dcea06f990c8033eaf98f6`

**Add kernel non-parametric regression**

0.16.4 (2019-03-14)
-------------------

`commit: 983b02ca54faa66941dcea06f990c8033eaf98f6`

**Add kernel non-parametric regression**

  - fix minor issue in memory collector that manifests with gcc-5.5+ and Ubuntu 18.04+
  - add three kernel non-parametrik regression models (see :ref:`postprocessors-kernel-regression`)
  - fix minor issues in moving average and regressogram

0.16.3 (2019-03-02)
-------------------

`commit: de699ab66d8438166d0ad2d55c74bf43a59d1fc4`

**Overhaul the trace collector**

  - update to Click version 7.0 (because underscores are replaced by dashes)
  - add automatic pairing of the static probes in trace collector
  - add fault-tolerant system to trace collector (now it does collect some profile even if it contains some corruption)
  - rework the internal format of traces

0.16.2 (2019-03-02)
-------------------

`commit: 77bed5eb7654274687fc0fa7130f28a6ff282fba`

**Fix and refactor the memory collector**

  - fix minor issue in average amount threshold checker, when average is 0
  - refactor memory collector
  - add proper documentation to memory collector
  - fix an ubuntu 18.04 issue, when dlsym() needed some bytes before libmalloc.so is properly loaded resulting into crash
  - add proper locking to memory collector

0.16.1 (2019-03-01)
-------------------

`commit: 04cd6a2dc788f73d21c23554ff2ab8174af67dbd`

**Add moving average postprocessor**

  - add moving average postprocessor, other of the non-parametric analysis
  - minor fixes in regressogram (refactor and documentation)
  - add `perun fuzz` command which does a performance fuzzing
  - remodel runner functions to generators

0.16 (2019-02-16)
-----------------

`commit: 04cd6a2dc788f73d21c23554ff2ab8174af67dbd`

**Add regressogram postprocessor**

  - add --version option to perun cli, so it shows version of perun (d'oh!)
  - extend scatterplot to support step function rendering (for regressogram)
  - add regressogram postprocessor, one of the non-parametric analysis

0.15.4 (2018-08-13)
-------------------

`commit: b1e2e3bdcca839efcf7a59ebb8fdbd2b8fc38888`

**Add cleanup procedures to Trace collector**

  - add cleanup procedures to trace collector (so it properly kills systemtap modules)
  - fix setup.py versions
  - make clusterizer less verbose
  - fix wrong parameter name in trace collector

0.15.3-hotfix (2018-08-02)
--------------------------

`commit: a9b46ed478258bbcd8292df0775a14e69b7db329`

**Hotfix unused workload parameter in trace collector**

  - hotfix missing workload parameter in trace collector


0.15.3 (2018-08-01)
-------------------

`commit: a9b46ed478258bbcd8292df0775a14e69b7db329`

**Extract trace configuration automatically**

  - rename complexity collector to **trace**
  - fix minor issues with trace collector
  - add basic support for parallel programs in trace collector
  - add basic support for non-terminating programs (--timeout) in trace collector
  - fix minor issues in incorrect piping (class with ||)
  - add lookup of profiled functions in trace collector

0.15.2 (2018-07-20)
-------------------

`commit: a9b46ed478258bbcd8292df0775a14e69b7db329`

**Upgrade Trace collector architecture**

  - update the cli of the :ref:`collectors-trace` with new options
  - add support for static and dynamic probing of the binaries (hence allow custom user probes)
  - fix minor issues
  - rework the architecture of system-tap collector to work as a daemon

0.15.1 (2018-07-17)
-------------------

`commit: f137abac6c428fc5e580dfa0fc9446c65ac30e4c`

**Rehaul the notion of workloads**

  - refactor check modules
  - add ``pending tag range`` to ``perun add`` command to add more profiles at once
  - add ``index tag rage`` to ``perun rm`` command to remove more profiles at once
  - fix the issue with wrong sort order and tags (now :ckey:`format.sort_profiles_by` sets the option in local)
  - add support for workload generators
  - implement integer workload generator that generates workload from the integer interval
  - implement singleton workload generator that generates single workload
  - implement string workload generator that generates random strings
  - implement file workload generator that generates random text files
  - add :ckey:`generators.workload` for specification of workload generators in config
  - remodel the notion of workloads to accept the workload generators to allow other style of workloads
  - add two modes of workload generation (one that merges the profiles into one; and one which gradually generates profiles)
  - add default workload generators to shared configuration

0.15 (2018-06-20)
-----------------

`commit: 6bb792fd8e172ab6c97a3cd1ac517bfe416b6c85`

**Extend the suite of change detection methods**

  - add fast check degradation check method (:ref:`degradation-fast-check`)
  - add linear regression based degradation check method (:ref:`degradation-lreg`)
  - add polynomial regression based degradation check method (:ref:`degradation-preg`)
  - rename regression models to full names
  - fix divisions by zero in several places in regression analysis
  - rename the api of several regression functions

0.14.4 (2018-06-17)
-------------------

`commit: 4e36142252e123f3e8e6422583c71383adc9fc30`

**Refactor the code**

  - fix various linting issues (e.g. too long lines)
  - remove unused code and function (e.g. in memory)
  - fix minor issues
  - extend the test suite with several more tests
  - flatten the test hierarchy
  - remove alloclist view (query+convert imported in python is more powerful)
  - renew the rest of the old documentation format
  - extract path and type function parameters from vcs api
  - refactor pcs module and remove pcs as argument from all of the functions
  - fix various codacy issues
  - refactor cli module by moving callbacks, renaming functions and removing redundant functions

0.14.3 (2018-06-12)
-------------------

`commit: a2820c0cb50cff5b758a3d01ca7b8e356af5d2cf`

**Extend utils module**

  - print timing of various collection phases
  - add :ckey:`degradation.log_collect` to store the output of precollect phase in isolated logs
  - add working ``--compute-missing`` parameter to check group, which temporarily sets the precollection
  - add repetition of the time collector
  - add predefined configuration templates
  - add automatic lookup of candidate executable and workloads for user configuration (see :ref:`config-templates`)
  - add ``perun config reset`` command to allow resetting of configuration to different states
  - extend the utils module with ELF helper functions
  - extend the utils with non-blocking subprocess calls
  - extend the utils with binary files lookup

0.14.2 (2018-05-15)
-------------------

`commit: 0faaa74097a159c4b441d65415dba504265c2059`

**Rehaul the command line output**

  - fix issue with pending tags not being sorted ;)
  - fix the issue with incorrectly flattened values in query
  - extend the memory collector to include the allocation order as resource
  - add loading and storing of performance change records
  - add short printed results for found degradations
  - update the default generated config
  - remake the output of time collector
  - fix issue with integer workloads
  - fix issue with non-sorted index profiles
  - fix issue with memory collector not removing the unreachable allocations
  - add vcs history tree to log (prints the context of the vcs tree)
  - remodel the output of the degradation checks
  - switch the colour of optimizations to green (instead of blue)
  - colour tainted (containing degradation) and fixed (containing optimization) branches in vcs history
  - add short summary of degradations to each minor version in graph
  - add semantic ordering of uids (used in outputs)
  - add vcs history to output of perun run matrix
  - make perun check precollect phase silent (until we figure out the better way?)
  - add streaming to the history (so it is not output when everything is done)
  - make two versions of run_jobs (one with history and one without)
  - refactor some modules to remove unnecessary dependencies
  - add information about degradations to perun status and log

0.14.1 (2018-04-19)
-------------------

`commit: b7922d7c1bbe7ea89fe735c93cf1e6c8a7604765`

**Extend the automation**

  - add two new options to regression analysis module (see :ref:`postprocessors-regression-analysis` for more details)
  - fix minor issues in regression analysis and scatter plot module
  - fix issue with non-deterministic ordering in flattening the values by convert
  - add different ordering to perun status profiles (now they are ordered by time)
  - add more boxes to the output of the perun status profiles (bundled per five profiles)
  - add :ckey:`format.sort_profiles_by` configuration key to allow sorting of profiles in ``perun status`` by different keys
  - add ``--sort-by`` option to ``perun status`` to allow sorting of profiles in ``perun status``
  - fix minor things in documentation
  - add few helper function for CLI and profiles
  - rename origin in ProfileInfo to source (class of names)
  - fix typos in documentation
  - remake walk major version to return MajorVersion object, with head and major version name
  - add helper function for loading the profile out of profile info
  - extend the api of the vcs (with storing/restoring the state, checkout and dirty-testing)
  - add :ckey:`profiles.register_after_run` configuration key to automatically register profiles after collection
  - add :ckey:`execute.pre_run` config key for running commands before execution of matrix
  - add helper function for safely getting config key
  - add ``--minor-version`` parameter to ``perun collect`` and ``perun run`` to run the collection over different minor version
  - add ``--crawl-parents`` parameter to allow ``perun collect`` and ``perun run`` to collect the data for both minor version and its predecessors
  - add checking out of the minor version, and saving the state, to collection of profiles
  - add :ckey:`degradation.collect_before_check` configuration key for automatically collect profiles before running degradation check

0.14 (2018-03-27)
-----------------

`commit: 3e56911baad6a7cd0ab0b90b23c6edbc57abeb43`

**Add clusterization postprocessor**

  - add clusterizer postprocessor (see :ref:`postprocessors-clusterizer`)
  - add helper function for flattening single resources
  - fixed profiles generated by time in tests

0.13 (2018-03-27)
-----------------

`commit: 9642c1dcd7ba39b91ef791039690f5be79312dd2`

**Add SystemTap based complexity collector**

  - add SystemTap based complexity collector (see :ref:`collectors-trace` for more details)
  - add ``perun utils create`` command (see :ref:`cli-utils-ref` for more details) for creating new modules according to stored templates
  - fix issue with getting config hierarchy, when outside of any perun scope

0.12.1 (2018-03-08)
-------------------

`commit: 96ef4443244568260e5dd25fa4cde5230eba8a36`

**Update project readme**

  - update the project readme
  - add compiled documentation

0.12 (2018-03-05)
-----------------

`commit: 7ac008e0a7be32d5ddfceb3cbe7042036323f82d`

**Add basic testing of performance changes between profiles**

  - add command for checking performance changes between two isolate profiles
  - add command for checking performance changes in given minor version
  - add command for checking performance changes within the project history
  - add two basic methods of checking performance changes
  - add two options to config (see :ckey:`degradation.strategies` and :ckey:`degradation.apply`)
    to customize performance checking
  - add caching to recursive config lookup
  - add recursive gathering of options from config
  - fix nondeterministic tests
  - define structure for representing the result of performance change
  - add basic implementation of performance change detectors

0.11.1 (2018-02-28)
-------------------

`commit: 8a6b1ac90c4cfca6f11546d0d3c4aa4fbe2000c3`

**Enhance the regression model suite**

  - fix issues when reading configuration with error
  - enhance the regression model suite by improving quadratic and constant models
  - rename the tags to different format (%tag%)
  - add support for shortlog formatting string
  - fix issue with postprocessing information being lost
  - add options for changing filename template
  - remodel automatic generation of profile names (now templatable; see :ckey:`format.output_profile_template`)
  - add runtime config
  - break config command to three (get, set, edit)
  - rename some configuration options
  - fix issue with missing header parts in profiles
  - fix issue with incorrect parameter
  - add global.paging option (see :ckey:`general.paging`)
  - improve bokeh outputs (with click policy, and better lines)
  - other various fixes

0.11 (2017-11-27)
-----------------

**Adding proper documentation**

`commit: a2ad710aafa171dfc6974c7121b572ee3ea2033b`

  - add HTML and latex documentation
  - refactor the documentation of publicly visible modules
  - add additional figures and examples of outputs and profiles
  - switch order of initialization of Perun instances and vcs
  - break vcs-params to vcs-flags and vcs-param
  - fix the issue with missing index
  - enhance the performance of Perun (guarding, rewriting to table lookup, or lazy inits)
  - add loading of yaml parameters from CLI

0.10.1 (2017-10-24)
-------------------

**Remodeling of the  regression analysis interface**

`commit: 14ce41c28d4d847ed2c74eac6a2dbfe7644cfd93`

  - refactor the interface of regression analysis
  - update the regression analysis error computation
  - add new parameters for plotting models
  - reduce number of specific computation functions
  - update the architecture (namely the interface)
  - update the documentation of regression analysis and parameters for cli
  - update the regressions analysis error computation
  - add constant model
  - add paging for perun log and status
  - rename converters and transformations modules

0.10 (2017-10-10)
-----------------

**Add Scatter plot visualization module**

`commit: f0d9785639e5c03a994eb439d54206722a455da3`

  - add scatter plot as new visualisation module (basic version with some temporary workarounds)
  - fix bisection method not producing model for some intervals
  - add examples of scatter plot graphs

0.9.2 (2017-09-28)
------------------

**Extend the regression analysis module**

`commit: 12c06251193701356685e8163a7ef8ce8b7d9f2a`

  - add transformation of models to plotable data points
  - add helper functions for plotting models
  - add support of regression analysis extensions

0.9.1 (2017-09-24)
------------------

**Extend the query module**

`commit: bf8ff341cfa942b82093850c63655b79674ea615`

  - add proper testing to query module
  - polish the messy conftest.py
  - add support generators and fixtures for query profiles
  - extend the profile query module with key values and models queries

0.9 (2017-08-31)
----------------

**Add regression analysis postprocessing module**

`commit: 2b3d0d637699ae35b36672df3ce4c14fa0fed701`

  - add regression analysis postprocessor module
  - add example resulting profiles


0.8.3 (2017-08-31)
------------------

`commit: e47f5588e834fd70042bb18ea53a7d76f75cc8b7`

**Update and fix complexity collector**

  - fix several minor issues with complexity collector
  - polish the standard of the generated profile
  - add proper testinr for cli
  - refactor according to the pylint
  - fix bug where vector would not be cleared after printing to file
  - remove code duplication in loop specification
  - fix different sampling data structure for job and complexity cli
  - fix some minor details with cli usage and info output

0.8.2 (2017-07-31)
------------------

**Update the command line interface of complexity collector**

`commit: 1451ae054e77e81bf0aa4930639bf323c09c510e`

  - add new options to complexity collector interface
  - add thorough documentation
  - refactor the implementation

0.8.1 (2017-07-30)
------------------

**Update the performance of command line interface**

`commit: 1fef373e8899b3ff0b0525ec99da91ba7a67fac0`

  - add on demand import of big libraries
  - optimize the memory collector by minimizing subprocess calls
  - fix issue with regex in memory collector
  - add caching of memory collector syscalls
  - extend cli of add and remove to support multiple args
  - extend the massaging of parameters for cli
  - remodel the config command
  - add support for tags in command line
  - enhance the status output of the profile list
  - enhance the default formatting of config
  - add thorough validity checking of bars/flow params

0.8 (2017-07-03)
----------------

**Add flame graph visualization**

`commit: 56a29c807f2d7ad34b7af6002e5ebf90c717e8d7`

  - add flame graph visualization module

0.7.2 (2017-07-03)
------------------

**Refactor flow graph to a more generic form**

`commit: eb33811236575599fc9aa82ce417c492be22d79b`

  - refactor flow to more generic format
  - work with flattened pandas.DataFrame format
  - use set of generators and queries for manipulation with profiles
  - make the cli API generic
  - polish the visual apeal of flow graphs
  - simplify output to bokeh.charts.Area
  - add basic testing of bokeh flow graphs
  - fix the issue with additional layer in memory profs

0.7.1 (2017-06-30)
------------------

**Refactor bar graph to a more generic form**

`commit: 5942e0b1aa8cc09ce0e22b030c3ec17dfdce0556`

  - refactor bars to more generic format
  - work with flattened pandas.DataFrame format
  - make the cli API generic
  - polish the visual apeal of bars graph
  - add unique colour palette to bokeh graphs
  - fix minor issue with matrix in config
  - add massaging of params for show and postprocess

0.7 (2017-06-26)
----------------

**Add bar graph visualization**

`commit: a0f1a4921ecf9ef8f5b7c14ba42442fc589581ed`

  - integrate bar graph visualization

0.6 (2017-06-26)
----------------

**Add Flow graph visualization**

`commit: 5683141b2e622af871eabc1c7259654151177256`

  - integrate flow graph visualization

0.5.1 (2016-06-22)
------------------

**Fix issues in memory collector**

`commit: 28560e8d47cb2b1e2087d7072c44584563f78870`

  - extend the CLI for memory collect
  - annotate phases of memory collect with basic informations
  - add checks for presence of debugging symbols
  - fix in various things in memory collector
  - extend the testing of memory collector

0.5 (2016-06-21)
----------------

**Add Heap map visualization**

`commit: 6ac6e43080f0a9b0c856636ed5ae12ee25a3d4df`

  - integrate Heap map visualization
  - add thorough testing of heap and heat map
  - refactor profile converting
  - refactor duplicate blobs of code
  - add animation feature
  - add origin to profile so it can be compared before adding profile
  - add more smart lookup of the profile for add
  - add choices for collector/vcs/postprocessor parameters in cli
  - simplify adding parameters to collectors/postprocessors
  - add support for formatting strings for profile list
  - refactor log and status function
  - add basic testing for the command line interface
  - switch interactive configuration to using editor
  - implement wrappers for collect and postprocessby
  - rename 'bin' keyword to 'cmd' in stored profiles
  - add basic testing of the collectors and commands

0.4.2 (2017-05-31)
------------------

**Collective fixes mostly for Memory collector**

`commit: 4d94299bc196292284995aabdce0c702e76b33ca`

  - fix a collector issue with zero value addresses
  - add checking validity of the looked up minor version
  - fix issue with incorrect parameter of the NotPerunRepositoryException
  - raise exception when the profile is in incorrect json syntax
  - catch error when minor head could not be found
  - add exception for errors in wrapped VCS
  - add exception for incorrect profile format
  - raise NotPerunRepository, when Perun is not located on path
  - fix message when git was reinitialized
  - catch exceptions for init

0.4.1 (2017-05-15)
------------------

**Collective fixes mosty for Complexity collector**

`commit: 13bebd88613fce58458d50207aea01ee7f672f86`

  - fixed size data container growth if functions were sampled
  - enhance the perun status with info about untracked profiles
  - add colours to printing of profile list (red for untracked)
  - add output of untracked profiles to perun status
  - fix issue with postprocessor parameter rewritten by local variable

0.4 (2017-03-17)
----------------

**Add Complexity collector**

`commit: 323228f95050e52041b47af899eaea6e90eb0605`

  - add complexity collector module


0.3 (2017-03-14)
----------------

**Adding Memory Collector**

`commit: 558ae1eee3acd370c519ac39e774d7fe05d23e35`

  - add memory collector module
  - fix the issue with detached head state and perun status
  - add simple, but interactive, initialization of the local config

0.2 (2017-03-07)
----------------

**Add basic job units**

`commit: 7994b5618eb27684da57ce0941f4f58604ac29ea`

  - add the normalizer postprocessor
  - add the time collector
  - refactor the git module to use the python package
  - add loadinng of config from local yml
  - refactor construction of job matrix
  - remove cmd from job tuple and rename params to args
  - break perun run to run matrix (from config) and run job (from stdout)
  - fix issue of assuming different structure of profile
  - add functionality of creating and storing profiles
  - add generation of the profile name for given job
  - add storing of the profile at given path
  - add generation of profile out of collected data
  - update the params between the phases
  - polish the perun --short header
  - various minor tweaks for outputs
  - change init-vcs-* options to just vcs-*
  - fix an issue with incorrectly outputed comma if no profile type was present
  - fix an issue with loading profile having two modes (compressed and uncompressed)
  - implement base logic for calling collectors and postprocessors
  - enhance output of profile numbers in perun log and status with colours and types
  - add header for short info
  - add colours to the header
  - add base implementation of perun show
  - fix loading of compressed file
  - polish output of perun log and status by adding indent, colours and padding
  - fix an issue with adding non-existent profile
  - fix multiple adding of the same entry
  - fix an issue when the added entry should go to end of index

0.1 (2017-02-22)
----------------

**First partially working implementation**

`commit: 4dd5ee3c638570489d60c50ca41b519029da9007`

  - add short printing of minor version info (--short-minors | -s option)
  - fix reverse output of log (oldest was displayed first)
  - implement simplistic perun log outputing minor version history and profile numbers
  - fix an incorrect warning about already tracked profiles
  - add removal of the entry from the index
  - add registering of  files to the minor version index
  - refactor according to pylint
  - add base implementation of perun log
  - add base implementation of perun status
  - add base implementation of perun add
  - add base implementation of perun rm
  - add base implementation of perun init
  - add base implementation of perun config
  - add base commandline interface through click

0.0 (2016-12-10)
----------------

**Initial minimalistic repository**

`commit: 2a6d1e65e5f3871e091d395789b9fd44450ef9e4`

  - empty root
