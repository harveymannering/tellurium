Things I would or might change about tellurium
---------------------------------------
 - prevent plots when you run the tests
 - We should use be using the typing library
    - so IDE's can provide us with type information 
 - Move all tests to a "tests" folder in the top level of the repository
 - setup coverage when pushed from travis
 - Embed roadrunner inside tellurium as a submodule. Then we configure 
   cmake to install directly into tellurium folder and distribute with 
   tellurium. 
 - add classifiers to setup script
 - Update dependency versions from requirements.txt one by one, run the tests 
   and see whether we can use newer versions of these libraries?
   - The "install_requires" field has different dependency versions to the requirement.txt file!
      - Make install_requires read from requirements, that way we dont have this problem. 
 - Update "contributing guidelines"
    - We do not want people directly contributing to master branch. Its like you want people to break your code.
 - Some people are using tox, others pytest and others still are using nosetests. All should work 
   fine but there might be differences. Run tests with all of them. Compare. Then pick one and recommend. 
 - delete build.sh - I think its unnecessary. 
    - similarly on windows - remoce bld.bat
    - Why have a build script when the build command is just "python setup.py install"?
 - What is meta.yml? Do some googling
 - Why doesn't py38 work again?
 - What is NEWS? I would delete. 
 - Delete the manifest.in, we are using "install_requires" in the setup script instead.
 - figure out how to make matplotlib stop issuing warnings. 
 - There is some commented out code in engine_mpl
 - I would argue that vizualization and plotting should be under the same namespace. 
 - Issues on github should probably get worked through. 
 
Things I've already changed
-----------------------------
- make long description read the readme.md in python setupscript
- Added the platforms key to setup.py
- added py37 and py38 to tox.ini