# Copyright (c) 2019, NVIDIA CORPORATION.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from cugraph.structure import graph_wrapper
import cudf
import numpy as np


def null_check(col):
    if col.null_count != 0:
        raise ValueError('Series contains NULL values')


class Graph:
    """
    cuGraph graph class containing basic graph creation and transformation
    operations.
    """
    def __init__(self):
        """
        Returns
        -------
        G : cuGraph.Graph.

        Examples
        --------
        >>> import cuGraph
        >>> G = cuGraph.Graph()
        """
        self.graph_ptr = graph_wrapper.allocate_cpp_graph()

        self.edge_list_source_col = None
        self.edge_list_dest_col = None
        self.edge_list_value_col = None

        self.adj_list_offset_col = None
        self.adj_list_index_col = None
        self.adj_list_value_col = None

    def __del__(self):
        self.delete_edge_list()
        self.delete_adj_list()
        self.delete_transposed_adj_list()

        graph_wrapper.release_cpp_graph(self.graph_ptr)

    def clear(self):
        """
        Empty this graph. This function is added for NetworkX compatibility.
        """
        self.delete_edge_list()
        self.delete_adj_list()
        self.delete_transposed_adj_list()

    def add_edge_list(self, source_col, dest_col, value_col=None, copy=False):
        """
        Initialize a graph from the edge list. It is an error to call this
        method on an initialized Graph object. The passed source_col and
        dest_col arguments wrap gdf_column objects that represent a graph
        using the edge list format.
        Source and destination indices must be in the range [0, V) where V is
        the number of vertices. They must be 32 bit integers. Please refer to
        cuGraph's renumbering feature if your input does not match these
        requierments. When using cudf.read_csv to load a CSV edge list,
        make sure to set dtype to int32 for the source and destination
        columns.
        If value_col is None, an unweighted graph is created. If value_col is
        not None, a weighted graph is created.
        If copy is False, this function stores references to the passed objects
        pointed by source_col and dest_col. If copy is True, this funcion
        stores references to the deep-copies of the passed objects pointed by
        source_col and dest_col.
        Undirected edges must be stored as directed edges in both directions.

        Parameters
        ----------
        source_col : cudf.Series
            This cudf.Series wraps a gdf_column of size E (E: number of edges).
            The gdf column contains the source index for each edge.
            Source indices must be in the range [0, V) (V: number of vertices).
            Source indices must be 32 bit integers.
        dest_col : cudf.Series
            This cudf.Series wraps a gdf_column of size E (E: number of edges).
            The gdf column contains the destination index for each edge.
            Destination indices must be in the range [0, V) (V: number of
            vertices).
            Destination indices must be 32 bit integers.
        value_col : cudf.Series, optional
            This pointer can be ``none``.
            If not, this cudf.Series wraps a gdf_column of size E (E: number of
            edges).
            The gdf column contains the weight value for each edge.
            The expected type of the gdf_column element is floating point
            number.

        Examples
        --------
        >>> M = cudf.read_csv('datasets/karate.csv', delimiter=' ',
        >>>                   dtype=['int32', 'int32', 'float32'], header=None)
        >>> sources = cudf.Series(M['0'])
        >>> destinations = cudf.Series(M['1'])
        >>> G = cugraph.Graph()
        >>> G.add_edge_list(sources, destinations, None)
        """
        null_check(source_col)
        null_check(dest_col)
        if value_col is not None:
            null_check(value_col)
        if source_col.dtype != np.int32:
            raise TypeError("cugraph currently supports only 32bit integer"
                            "vertex ids.")
        if dest_col.dtype != np.int32:
            raise TypeError("cugraph currently supports only 32bit integer"
                            "vertex ids.")

        # Create temporary references first as the member variables should not
        # be updated on failure.
        if copy is False:
            tmp_source_col = source_col
            tmp_dest_col = dest_col
            tmp_value_col = value_col
        else:
            tmp_source_col = source_col.copy()
            tmp_dest_col = dest_col.copy()
            tmp_value_col = value_col.copy()

        graph_wrapper.add_edge_list(self.graph_ptr,
                                    tmp_source_col,
                                    tmp_dest_col,
                                    tmp_value_col)

        # Increase the reference count of the Python objects to avoid premature
        # garbage collection while they are still in use inside the gdf_graph
        # object.
        self.edge_list_source_col = tmp_source_col
        self.edge_list_dest_col = tmp_dest_col
        self.edge_list_value_col = tmp_value_col

    def view_edge_list(self):
        """
        Display the edge list. Compute it if needed.
        """
        source_col, dest_col = graph_wrapper.view_edge_list(self.graph_ptr)

        return source_col, dest_col

    def delete_edge_list(self):
        """
        Delete the edge list.
        """
        graph_wrapper.delete_edge_list(self.graph_ptr)

        # decrease reference count to free memory if the referenced objects are
        # no longer used.
        self.edge_list_source_col = None
        self.edge_list_dest_col = None
        self.edge_list_value_col = None

    def add_adj_list(self, offset_col, index_col, value_col=None, copy=False):
        """
        Initialize a graph from the adjacency list. It is an error to call this
        method on an initialized Graph object. The passed offset_col and
        index_col arguments wrap gdf_column objects that represent a graph
        using the adjacency list format.
        If value_col is None, an unweighted graph is created. If value_col is
        not None, a weighted graph is created.
        If copy is False, this function stores references to the passed objects
        pointed by offset_col and index_col. If copy is True, this funcion
        stores references to the deep-copies of the passed objects pointed by
        offset_col and index_col.
        Undirected edges must be stored as directed edges in both directions.

        Parameters
        ----------
        offset_col : cudf.Series
            This cudf.Series wraps a gdf_column of size V + 1 (V: number of
            vertices).
            The gdf column contains the offsets for the vertices in this graph.
            Offsets must be in the range [0, E] (E: number of edges).
        index_col : cudf.Series
            This cudf.Series wraps a gdf_column of size E (E: number of edges).
            The gdf column contains the destination index for each edge.
            Destination indices must be in the range [0, V) (V: number of
            vertices).
        value_col : cudf.Series, optional
            This pointer can be ``none``.
            If not, this cudf.Series wraps a gdf_column of size E (E: number of
            edges).
            The gdf column contains the weight value for each edge.
            The expected type of the gdf_column element is floating point
            number.

        Examples
        --------
        >>> M = cudf.read_csv('datasets/karate.csv', delimiter=' ',
        >>>                   dtype=['int32', 'int32', 'float32'], header=None)
        >>> M = M.to_pandas()
        >>> M = scipy.sparse.coo_matrix((M['2'],(M['0'],M['1'])))
        >>> M = M.tocsr()
        >>> offsets = cudf.Series(M.indptr)
        >>> indices = cudf.Series(M.indices)
        >>> G = cugraph.Graph()
        >>> G.add_adj_list(offsets, indices, None)
        """
        null_check(offset_col)
        null_check(index_col)
        if value_col is not None:
            null_check(value_col)
        if offset_col.dtype != np.int32:
            raise TypeError("cugraph currently supports only 32bit integer"
                            "offsets.")
        if index_col.dtype != np.int32:
            raise TypeError("cugraph currently supports only 32bit integer"
                            "vertex ids.")

        # Create temporary references first as the member variables should not
        # be updated on failure.
        if copy is False:
            tmp_offset_col = offset_col
            tmp_index_col = index_col
            tmp_value_col = value_col
        else:
            tmp_offset_col = offset_col.copy()
            tmp_index_col = index_col.copy()
            tmp_value_col = value_col.copy()

        graph_wrapper.add_adj_list(self.graph_ptr,
                                   tmp_offset_col,
                                   tmp_index_col,
                                   tmp_value_col)

        # Increase the reference count of the Python objects to avoid premature
        # garbage collection while they are still in use inside the gdf_graph
        # object.
        self.adj_list_offset_col = tmp_offset_col
        self.adj_list_index_col = tmp_index_col
        self.adj_list_value_col = tmp_value_col

    def view_adj_list(self):
        """
        Display the adjacency list. Compute it if needed.
        """
        offset_col, index_col = graph_wrapper.view_adj_list(self.graph_ptr)

        return offset_col, index_col

    def delete_adj_list(self):
        """
        Delete the adjacency list.
        """
        graph_wrapper.delete_adj_list(self.graph_ptr)

        # decrease reference count to free memory if the referenced objects are
        # no longer used.
        self.adj_list_offset_col = None
        self.adj_list_index_col = None
        self.adj_list_value_col = None

    def add_transposed_adj_list(self):
        """
        Compute the transposed adjacency list. It is an error to call this
        method on an uninitialized Graph object or a Graph object without an
        existing edge list.
        """
        graph_wrapper.add_transposed_adj_list(self.graph_ptr)

    def view_transposed_adj_list(self):
        """
        Display the transposed adjacency list. Compute it if needed.
        """
        offset_col, index_col = graph_wrapper.view_transposed_adj_list(
                                    self.graph_ptr)

        return offset_col, index_col

    def delete_transposed_adj_list(self):
        """
        Delete the transposed adjacency list.
        """
        graph_wrapper.delete_transposed_adj_list(self.graph_ptr)

    def get_two_hop_neighbors(self):
        """
        Compute vertex pairs that are two hops apart. The resulting pairs are
        sorted before returning.

        Returns
        -------
        df : cudf.DataFrame
            df['first'] : cudf.Series
                the first vertex id of a pair.
            df['second'] : cudf.Series
                the second vertex id of a pair.
        """
        df = graph_wrapper.get_two_hop_neighbors(self.graph_ptr)

        return df

    def number_of_vertices(self):
        """
        Get the number of vertices in the graph.
        """
        num_vertices = graph_wrapper.number_of_vertices(self.graph_ptr)

        return num_vertices

    def number_of_nodes(self):
        """
        An alias of number_of_vertices(). This function is added for NetworkX
        compatibility.
        """
        return self.number_of_vertices()

    def number_of_edges(self):
        """
        Get the number of edges in the graph.
        """
        num_edges = graph_wrapper.number_of_edges(self.graph_ptr)

        return num_edges

    def in_degree(self, vertex_subset=None):
        """
        Compute veretx in-degree. Vertex in-degree is the number of edges
        pointing into the vertex. By default, this method computes vertex
        degrees for the entire set of vertices. If vertex_subset is provided,
        this method optionally filters out all but those listed in
        vertex_subset.

        Parameters
        ----------
        vertex_subset : cudf.Series or iterable container, optional
            A container of vertices for displaying corresponding in-degree.
            If not set, degrees are computed for the entire set of vertices.

        Returns
        -------
        df : cudf.DataFrame
            GPU data frame of size N (the default) or the size of the given
            vertices (vertex_subset) containing the in_degree. The ordering is
            relative to the adjacency list, or that given by the specified
            vertex_subset.

            df['vertex'] : cudf.Series
                The vertex IDs (will be identical to vertex_subset if
                specified).
            df['degree'] : cudf.Series
                The computed in-degree of the corresponding vertex.

        Examples
        --------
        >>> M = cudf.read_csv('datasets/karate.csv', delimiter=' ',
        >>>                   dtype=['int32', 'int32', 'float32'], header=None)
        >>> sources = cudf.Series(M['0'])
        >>> destinations = cudf.Series(M['1'])
        >>> G = cugraph.Graph()
        >>> G.add_edge_list(sources, destinations, None)
        >>> df = G.in_degree([0,9,12])
        """
        return self._degree(vertex_subset, x=1)

    def out_degree(self, vertex_subset=None):
        """
        Compute veretx out-degree. Vertex out-degree is the number of edges
        pointing out from the vertex. By default, this method computes vertex
        degrees for the entire set of vertices. If vertex_subset is provided,
        this method optionally filters out all but those listed in
        vertex_subset.

        Parameters
        ----------
        vertex_subset : cudf.Series or iterable container, optional
            A container of vertices for displaying corresponding out-degree.
            If not set, degrees are computed for the entire set of vertices.

        Returns
        -------
        df : cudf.DataFrame
            GPU data frame of size N (the default) or the size of the given
            vertices (vertex_subset) containing the out_degree. The ordering is
            relative to the adjacency list, or that given by the specified
            vertex_subset.

            df['vertex'] : cudf.Series
                The vertex IDs (will be identical to vertex_subset if
                specified).
            df['degree'] : cudf.Series
                The computed out-degree of the corresponding vertex.

        Examples
        --------
        >>> M = cudf.read_csv('datasets/karate.csv', delimiter=' ',
        >>>                   dtype=['int32', 'int32', 'float32'], header=None)
        >>> sources = cudf.Series(M['0'])
        >>> destinations = cudf.Series(M['1'])
        >>> G = cugraph.Graph()
        >>> G.add_edge_list(sources, destinations, None)
        >>> df = G.out_degree([0,9,12])
        """
        return self._degree(vertex_subset, x=2)

    def degree(self, vertex_subset=None):
        """
        Compute veretx degree. By default, this method computes vertex
        degrees for the entire set of vertices. If vertex_subset is provided,
        this method optionally filters out all but those listed in
        vertex_subset.

        Parameters
        ----------
        vertex_subset : cudf.Series or iterable container, optional
            A container of vertices for displaying corresponding degree. If not
            set, degrees are computed for the entire set of vertices.

        Returns
        -------
        df : cudf.DataFrame
            GPU data frame of size N (the default) or the size of the given
            vertices (vertex_subset) containing the degree. The ordering is
            relative to the adjacency list, or that given by the specified
            vertex_subset.

            df['vertex'] : cudf.Series
                The vertex IDs (will be identical to vertex_subset if
                specified).
            df['degree'] : cudf.Series
                The computed degree of the corresponding vertex.

        Examples
        --------
        >>> M = cudf.read_csv('datasets/karate.csv', delimiter=' ',
        >>>                   dtype=['int32', 'int32', 'float32'], header=None)
        >>> sources = cudf.Series(M['0'])
        >>> destinations = cudf.Series(M['1'])
        >>> G = cugraph.Graph()
        >>> G.add_edge_list(sources, destinations, None)
        >>> df = G.degree([0,9,12])
        """
        return self._degree(vertex_subset)

    def degrees(self, vertex_subset=None):
        """
        Compute veretx in-degree and out-degree. By default, this method
        computes vertex degrees for the entire set of vertices. If
        vertex_subset is provided, this method optionally filters out all but
        those listed in vertex_subset.

        Parameters
        ----------
        vertex_subset : cudf.Series or iterable container, optional
            A container of vertices for displaying corresponding degree. If not
            set, degrees are computed for the entire set of vertices.

        Returns
        -------
        df : cudf.DataFrame

            df['vertex'] : cudf.Series
                The vertex IDs (will be identical to vertex_subset if
                specified).
            df['in_degree'] : cudf.Series
                The in-degree of the vertex.
            df['out_degree'] : cudf.Series
                The out-degree of the vertex.

        Examples
        --------
        >>> M = cudf.read_csv('datasets/karate.csv', delimiter=' ',
        >>>                   dtype=['int32', 'int32', 'float32'], header=None)
        >>> sources = cudf.Series(M['0'])
        >>> destinations = cudf.Series(M['1'])
        >>> G = cugraph.Graph()
        >>> G.add_edge_list(sources, destinations, None)
        >>> df = G.degrees([0,9,12])
        """
        vertex_col, in_degree_col, out_degree_col = graph_wrapper._degrees(
                                                        self.graph_ptr)

        df = cudf.DataFrame()
        if vertex_subset is None:
            df['vertex'] = vertex_col
            df['in_degree'] = in_degree_col
            df['out_degree'] = out_degree_col
        else:
            df['vertex'] = cudf.Series(
                np.asarray(vertex_subset, dtype=np.int32))
            df['in_degree'] = cudf.Series(
                np.asarray([in_degree_col[i] for i in vertex_subset],
                           dtype=np.int32))
            df['out_degree'] = cudf.Series(
                np.asarray([out_degree_col[i] for i in vertex_subset],
                           dtype=np.int32))
            # is this necessary???
            del vertex_col
            del in_degree_col
            del out_degree_col

        return df

    def _degree(self, vertex_subset, x=0):
        vertex_col, degree_col = graph_wrapper._degree(self.graph_ptr, x)

        df = cudf.DataFrame()
        if vertex_subset is None:
            df['vertex'] = vertex_col
            df['degree'] = degree_col
        else:
            df['vertex'] = cudf.Series(np.asarray(
                vertex_subset, dtype=np.int32
            ))
            df['degree'] = cudf.Series(np.asarray(
                [degree_col[i] for i in vertex_subset], dtype=np.int32
            ))
            # is this necessary???
            del vertex_col
            del degree_col

        return df
