Perun: Lightweight Performance Version System
=============================================

![image](https://travis-ci.org/tfiedor/perun.svg?branch=master)
[![codecov](https://codecov.io/gh/tfiedor/perun/branch/master/graph/badge.svg)](https://codecov.io/gh/tfiedor/perun)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/c4002ae488f54aabb77920a0cc90b6f5)](https://www.codacy.com/app/tfiedor/perun?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=tfiedor/perun&amp;utm_campaign=Badge_Grade)
[![Maintainability](https://api.codeclimate.com/v1/badges/233e3e1a434815fee154/maintainability)](https://codeclimate.com/github/tfiedor/perun/maintainability)
[![GitHub tag](https://img.shields.io/github/tag/tfiedor/perun.svg)](https://github.com/tfiedor/perun)


<p align="center">
  <img src="figs/perun-logo.png">
</p>

Perun is an open source light-weight Performance Version System, which works as a wrapper over
existing Version Control Systems and in parallel manages performance profiles corresponding to
different versions of projects. Moreover, it offers a tool suite suitable for automation of the
performance regression test runs, postprocessing of existing profiles or effective interpretation of
the results.

<p align="center">
  <img width="460" height="300" src="figs/perun-vs-vcs.svg">
</p>

In particular, Perun has the following advantages over using databases or sole Version Control
Systems for the same purpose:

  1.  **Preserves Context**---each performance profile is assigned to a concrete
      minor version adding the functional context (i.e. code changes) of profiles.
      
  2.  **Provides Automation**---Perun allows one to easily automate the process
      of profile collection, eventually reducing the whole process to a
      single command. The specification of jobs is read from YAML files.
      
  3.  **Is Highly Generic**---supported format of the performance profiles is
      based on [JSON](https://www.json.org/). Perun tool suite 
      contains a basic set of visualizations, postprocessing and 
      collection modules, but it is easily extensible.
      
  4.  **Is Easy to use**---the workflow, interface and storage of Perun is
      heavily inspired by the git systems aiming at natural use. 

<p align="center">
  <img src="figs/perun-flow.svg">
</p>

Perun is intented to be used in two ways: (1) for a single developer (or a small team) as a complete
solution for automating, storing and interpreting performance of project or (2) as a dedicated store
for a bigger projects and teams. Its git-like design aims at easy distribution and simple interface
makes it a good store of profiles along with the context.

Installation
------------

You can install Perun as follows:

    git clone https://github.com/tfiedor/perun.git
    cd perun
    make init
    make install

These commands install Perun to your system as a runnable python package. You can then run Perun
safely from the command line using the `perun` command. Run either `perun --help` or see the [cli
documentation](https://tfiedor.github.io/perun/cli.html) for more information about running Perun
commands from command line. Note that depending on your OS and the location of Python libraries, you
might require root permissions to install Perun.

It is advised to verify that Perun is running correctly in your environment as follows:

    make test

### Installing Tracer Dependencies

The standard Perun installation does not automatically install the instrumentation frameworks
used by Tracer: SystemTap and eBPF. Installing these frameworks is optional when using Perun, 
although having at least one of them is required in order to run Tracer. Moreover, both frameworks 
rely on system-wide packages and thus should be installed directly by the user when needed.

#### SystemTap: Ubuntu

SystemTap can be installed using `apt-get`:

    sudo apt-get install systemtap

Furthermore, kernel debug symbols package must be installed in order to use SystemTap. For Ubuntu
16.04 and higher:

    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys C8CAB6595FDFF622 
    codename=$(lsb_release -c | awk  '{print $2}')
    sudo tee /etc/apt/sources.list.d/ddebs.list << EOF
    deb http://ddebs.ubuntu.com/ ${codename}      main restricted universe multiverse
    deb http://ddebs.ubuntu.com/ ${codename}-security main restricted universe multiverse
    deb http://ddebs.ubuntu.com/ ${codename}-updates  main restricted universe multiverse
    deb http://ddebs.ubuntu.com/ ${codename}-proposed main restricted universe multiverse
    EOF

    sudo apt-get update
    sudo apt-get install linux-image-$(uname -r)-dbgsym

To test that SystemTap works correctly, run the following command:

    stap -v -e 'probe vfs.read {printf("read performed\n"); exit()}'

For more information, see the [source](https://wiki.ubuntu.com/Kernel/Systemtap).

#### SystemTap: Fedora

SystemTap can be installed using `yum`:

    sudo yum install systemtap systemtap-runtime

Similarly to the Ubuntu case, additional kernel packages must be installed to run 
SystemTap properly:

    kernel-debuginfo
    kernel-debuginfo-common
    kernel-devel

Different Fedora versions use different methods for obtaining those packages. Please refer to
the [SystemTap setup guide](https://www.sourceware.org/systemtap/SystemTap_Beginners_Guide/using-systemtap.html#using-setup)

#### BCC: Ubuntu

Perun uses the [BCC (BPF Compiler Collection)](https://github.com/iovisor/bcc) frontend for the eBPF technology. 
We recommend obtaining the necessary packages from the IO Visor repository:

    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 4052245BD4284CDD
    echo "deb https://repo.iovisor.org/apt/$(lsb_release -cs) $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/iovisor.list
    sudo apt-get update
    sudo apt-get install bcc-tools libbcc-examples linux-headers-$(uname -r)

The default BCC installation uses bindings for Python 2, however, Perun requires bindings for
Python 3. To install them, run the following command:

    sudo apt-get install python3-bcc

#### BCC: Fedora

Installing BCC on Fedora is much easier. Simply run:

    sudo dnf install bcc python3-bcc

#### BCC: python virtualenv

Note that when using Perun in a Python virtual environment, the above installation instructions
are not enough. Since the Python `bcc` package is not available through `pip`, installing it
directly in a virtualenv using pip requirements list is not an option. A common workaround is
to copy the system-wide python `bcc` package installed in the previous step (`python3-bcc`) 
into the virtualenv packages.

To find the system python3 `bcc` package, run:

    python3 -c "import site; print(site.getsitepackages())"

which shows the potential global site-packages paths (not all of the paths must necessarily exist).
The package `bcc` should be located in at least one the listed path (otherwise the installation of 
`python3-bcc` must have failed in the previous step). The resulting path may look like e.g.:

    /usr/lib/python3/dist-packages

Run the same command with an activated virtualenv to get the list of site-packages paths local to
the virtualenv. As with the global site-packages path, not all of the listed paths must exist - usually 
only one truly does. E.g.:

    <prefix>/venv-3.8/lib/python3.8/site-packages

Next, copy the `bcc` package from the global site-packages to the virtualenv local site-packages:

    cp -r /usr/lib/python3/dist-packages/bcc <prefix>/venv-3.8/lib/python3.8/site-packages/

Now the `bcc` package should be available in the virtualenv python. Test the following command 
with activated virtualenv:

    python3 -c "import bcc"

which should successfully finish (i.e. `ModuleNotFoundError` should not be raised).

Developing
----------

Alternatively you can install Perun in development mode:

    git clone https://github.com/tfiedor/perun.git
    cd perun
    make init
    make dev

This method of installation allows you to make a changes to the code, which will be then reflected
by the installation.

Again, it is advised to verify that Perun is running correctly in your environment as follows:

    make test
    
If you are interested in contributing to Perun project, please refer to
[contributing](CONTRIBUTING) section. If you think your results could help others, please [send us
PR](https://github.com/tfiedor/perun/pull/new/develop), we will review the code and in case it is
suitable for wider audience, we will include it in our [upstream](https://github.com/tfiedor/perun).

But, please be understanding, we cannot fix and merge everything.

Getting Started
---------------

In order to start managing performance of your project tracked by `git`, go to its directory and run
the following:

    perun init --vcs-type=git --configure
    
This creates a parallel directory structure for Perun storage (stored in `.perun`), and runs the
initial configuration of the local project settings in text editor (by default `vim`). There you can
chose the set of collectors, postprocessors and specify which commands (and with which
configurations) should be profiled. See [configuration](https://tfiedor.github.io/perun/config.html)
for more details about perun's configuration.

Now start collecting the profiles for current version of your project:

    perun run matrix
    
This command collects set of profiles, according to the previously set configuration (see
[specification of job matrix](https://tfiedor.github.io/perun/jobs.html#job-matrix-format) for more
details). You can then view the list of collected and registered profiles, and visualize the
profiles (see [visualization overview](https://tfiedor.github.io/perun/views.html)), or check for
possible performance changes (see [degradation
documentation](https://tfiedor.github.io/perun/degradation.html)):

    # Show list of profiles
    perun status
    
    # Show the first generated profile using scatter plot
    perun show 0@p scatter -v
    
    # Register the first generated profile to current minor version
    perun add 0@p
    
Now anytime one can do code changes, commit them, rerun the collection phase, register new profiles
and check whether any change in performance can be detected:

    # Rerun the collection
    perun run matrix
    
    # Register the profiles for current minor version
    perun add 0@p
    
    # Run the degradation check
    perun check head

Features
--------

In the following, we list the foremost features and advantages of Perun:

  -   **Unified format**---we base our format of performance profiles on
  [JSON](https://www.json.org/).
  
  -   **Natural specification of Profiling Runs**---we base the specification of profiling jobs in
  [Yaml](http://yaml.org/) format.
      
  -   **Git-inspired Interface**---the cli is inspired by git version control systems and specifies
  commands like e.g. `add`, `remove`, `status`, or `log`.
      
  -   **Efficient storage**---performance profiles are stored compressed in the storage in parallel
  to versions of the profiled project inspired by git.
      
  -   **Multiplatform-support**---Perun is implemented in Python 3 and its implementation is
  supported both by Windows and Unix-like platforms.
      
  -   **Regression Analysis**---Perun's suite contains a postprocessing module for regression
  analysis of profiles (see [regression analysis
  documentation](https://tfiedor.github.io/perun/postprocessors.html#module-perun.postprocess.regression_analysis)),
  which supports several different strategies for finding the best predicting model for given data
  (such as linear, quadratic, or constant model).
      
  -   **Interactive Visualizations**---Perun's tool suite includes several visualization modules,
  some of them based on [Bokeh](https://bokeh.pydata.org/en/latest/) visualization library, which
  provides nice and interactive plots, in exchange of scalability.
      
  -   **Useful API for profile manipulation**---helper modules are provided for working with our
  profiles in external applications ---we have API for executing simple queries over the resources
  or other parts of the profiles, or convert and transform the profiles to different representations
  (e.g. pandas data frame). See [conversion
  api](https://tfiedor.github.io/perun/profile.html#module-perun.profile.convert) and [query
  api](https://tfiedor.github.io/perun/profile.html#module-perun.profile.query) for overview.
      
  -   **Automatic Detection of Performance Degradation**---we are currently exploring effective
  heuristics for automatic detection of performance degradation between two project versions (e.g.
  between two commits).

As a sneak peek, we are currently working and exploring the following featurues in near future of
the project:

  -   **Regular Expression Driven Collector**---collector based on parsing the standard text output
  for a custom specified metrics, specified by regular expressions.
      
  -   **Fuzzing Collector**---collector based on method of fuzz testing ---i.e. modifying inputs in
  order to force error or, in our case, a performance change.
      
  -   **Clustering Postprocessor**---we are exploring now how to make any profile usable for
  regression analysis.
      
  -   **Automatic Hooks**---the automatic hooks, that will allow to automate the runs of job matrix,
  automatic detection of degradation and efficient storage.
      
For more information about Perun's feature, please refer to our [extensive list of
features](https://tfiedor.github.io/perun/overview.html#list-of-features)!

Contributing
------------

If you'd like to contribute, please fork the repository and use a feature branch. Pull requests are
warmly welcome.

In case you run in some unexpected behaviour, error or anything suspicious, either contact us
directly through mail or [create a new Issue](https://github.com/tfiedor/perun/issues/new).

The architecture of Perun allows easy extension. In case you are interested in extending our tool
suite with new kinds of collectors, postprocessors or visualization methods, please refer to
appropriate sections in Perun's documentation (i.e. Create your own
[collector](https://tfiedor.github.io/perun/collectors.html#creating-your-own-collector),
[postprocessor](https://tfiedor.github.io/perun/postprocessors.html#creating-your-own-postprocessor) 
or [visualization](https://tfiedor.github.io/perun/views.html#creating-your-own-visualization)).

If you are interested in contributing to Perun project, please first refer to
[contributing](Contributing.md) section. If you think your custom module could help others, please
[send us PR](https://github.com/tfiedor/perun/pull/new/develop), we will review the code and in case
it is suitable for wider audience, we will include it in our
[upstream](https://github.com/tfiedor/perun).

But, please be understanding, we cannot fix and merge everything.

Links
-----

   -   Project repository : <https://github.com/tfiedor/perun>
   -   Issue tracker: <https://github.com/tfiedor/perun/issues>
       - In case of sensitive bugs like security vulnerabilities, please contact
       :   <TomasFiedor@gmail.com> directly instead of using issue tracker. We
           value your effort to improve the security and privacy of
           this project!
   -   Project documentation:
       - Online: <https://tfiedor.github.io/perun/>
       - Latest Typeset: <https://github.com/tfiedor/perun/blob/master/docs/pdf/perun.pdf>
     
Unrelated links:

   -   Check out our research group focusing on program analysis, static and dynamic analysis,
   formal methods, verification and many more:
   <http://www.fit.vutbr.cz/research/groups/verifit/index.php.en>

Licensing
---------

The code in this project is licensed under GNU GPLv3 license.

Acknowledgements
----------------

We thank for the support received from [Red Hat](https://www.redhat.com/en/global/czech-republic)
(especially branch of Brno), and Brno University of Technology 
([BUT FIT](https://www.fit.vutbr.cz/)).

Further we would like to thank the following individuals (in the
alphabetic order) for their (sometimes even just a little)
contributions:

  -   **Jan Fiedor** (Honeywell)---for feedback, and technical
      discussions;
  -   **Jirka Hladky** and his team (RedHat)---for technical discussions;
  -   **Martin Hruska** (BUT FIT)---for feedback, and technical
      discussions;
  -   **Petr Müller** (SAP)---for nice discussion about the project;
  -   **Michal Kotoun** (BUT FIT)---for feedback, and having faith in
      this repo;
  -   **Hanka Pluhackova** (BUT FIT)---for awesome logo, theoretical
      discussions about statistics, feedback, and lots of ideas;
  -   **Adam Rogalewicz** (BUT FIT)---for support, theoretical
      discussions, feedback;
  -   **Tomas Vojnar** (BUT FIT)---for support, theoretical discussions,
      feedback;
  -   **Jan Zeleny** (Red Hat)---for awesome support, and feedback.

Development of this tool has been supported by AQUAS project (Aggregated Quality Assurance for
Systems, https://aquas-project.eu/). This project has received funding from the Electronic Component
Systems for European Leadership Joint Undertaking under grant agreement No 737475. This Joint
Undertaking receives support from the European Union’s Horizon 2020 research and innovation
programme and Spain, France, United Kingdom, Austria, Italy, Czech Republic, Germany.

This tool as well as the information provided on this web page reflects only the author's view and
ECSEL JU is not responsible for any use that may be made of the information it contains.

<p align="center">
  <img src="figs/logo-excel.gif">
</p>

<p align="center">
  <img src="figs/logo-eu.jpg" width="33%">
</p>
 This project is co-funded by the European Union
