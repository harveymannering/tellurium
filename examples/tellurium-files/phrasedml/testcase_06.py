

# create a report only
report task1.time, task1.S1, task2.S1

# coupled ranges
repeat1 = repeat task1 for S1 in [1, 3, 5], S2 in uniform(0, 10, 3)
# set values in repeated Task & multiple tasks via same range
repeat2 = repeat [task1, task2] for X in uniform(0, 10, 100), mod1.S1 = X, mod2.S1 = X+3

# logUniform simulation
repeat3 = repeat task1 for S2 in logUniform(0, 10, 3), reset=true