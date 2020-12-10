#include <assert.h>
#include <stdio.h>
#include <unistd.h>

#define REPS 100
#define SLEEP_TIME 1000

// for both direct and indirect recursion in callgraph

int recursive_fun(int);

int foo(){
	recursive_fun(1);
}

int recursive_fun(int value){
	if (value == 3){
		foo();
	}
	else if (value == 2)
		recursive_fun(1);
	else
		return 0;
}


int main(int argc, char ** argv){
	FILE * fp = fopen(argv[1],"r");
	fclose(fp);
	fp = fopen(argv[1],"r");
	int num;
	fscanf(fp,"%d ",&num);
	if( num != 5 ){
		int i;
		for(i = 0; i < REPS; i++)
			usleep(SLEEP_TIME);
	}
	fclose(fp);
	recursive_fun(argc);
	foo();
	// foo();
	return 0;
}
