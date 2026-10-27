/* Establish that the installed host ASan runtime can launch before the suite. */
#include <stdlib.h>
int main(void) {
    volatile unsigned char *p = (volatile unsigned char *)malloc(1);
    if (!p) return 1;
    p[0] = 7;
    if (p[0] != 7) return 1;
    free((void *)p);
    return 0;
}
