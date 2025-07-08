#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <unistd.h>

int main(int argc, char ** const argv) {
	setuid(atoi(argv[1]));
	system(argv[2]);
	return 0;
}
