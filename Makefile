
###
## CircleCI development targets
#

.PHONY: circleci-validate
circleci-validate: .circleci/config.yml
	circleci config validate

# Override this on the make command to say which job to run
CIRCLEJOB ?= build
.PHONY: circleci-execute
.INTERMEDIATE: tmpconfig.yml
circleci-execute: .circleci/config.yml circleci-validate
ifeq ($(CIRCLECI),true)
	$(error "Don't run this target from within CircleCI!")
endif
	circleci config process $< > tmpconfig.yml
	circleci local execute -c tmpconfig.yml --job $(CIRCLEJOB)
