#include "sorts.h"
#include <iostream>
#include <sys/sdt.h>

const int MAX_SORT_ARR_LEN = 30;
const int SORT_ARR_LEN_INC = 5;


int main() {
    try
    {
        throw 20;
    }
    catch (int e)
    {
        std::cout << "An exception occurred. Exception Nr. " << e << std::endl;
    }
    // Run bad quicksort on different scales with reverse sorted input
	STAP_PROBE(PROV, BEFORE_CYCLE);
    for(int i = SORT_ARR_LEN_INC; i <= MAX_SORT_ARR_LEN; i += SORT_ARR_LEN_INC) {
        int *input = new int[i];

        for(int j = 0; j < i; j++) {
            input[j] = i - j - 1;
        }

        QuickSortBad(input, i);
        delete[] input;
    }
	STAP_PROBE(PROV, BEFORE_CYCLE_end);

	std::cout << "C++ sort" << std::endl;
    return 0;
}
