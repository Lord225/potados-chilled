/* Recursive Lomuto quicksort of sixteen native 16-bit integers.
 * The array lives in global RAM; recursive frames occupy the stack.
 */
int values[16] = {12, 4, 15, 1, 9, 0, 7, 14, 3, 11, 6, 2, 13, 8, 5, 10};

static int partition(int *array, int low, int high) {
    int pivot = array[high];
    int next = low;
    for (int current = low; current < high; ++current) {
        if (array[current] <= pivot) {
            int temporary = array[next];
            array[next] = array[current];
            array[current] = temporary;
            ++next;
        }
    }
    int temporary = array[next];
    array[next] = array[high];
    array[high] = temporary;
    return next;
}

static void quicksort(int *array, int low, int high) {
    if (low < high) {
        int pivot = partition(array, low, high);
        quicksort(array, low, pivot - 1);
        quicksort(array, pivot + 1, high);
    }
}

int main(void) {
    quicksort(values, 0, 15);
    for (int i = 0; i < 16; ++i) {
        if (values[i] != i)
            return 1;
    }
    return 0;
}
